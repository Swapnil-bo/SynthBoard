"""Dataset endpoints: upload, validate, preview, format conversion."""
import csv
import io
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from backend.config import MAX_UPLOAD_SIZE_BYTES, UPLOADS_DIR
from backend.db.database import get_db
from backend.models.dataset import (
    DatasetInfo,
    DatasetListResponse,
    DatasetPreviewRow,
    DatasetUploadResponse,
    FormatRequest,
    FormatResponse,
)
from backend.services.dataset_formatter import format_dataset
from backend.utils.validators import validate_extension, validate_file_content

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# ── Format detection helpers ──

ALPACA_KEYS = {"instruction", "output"}
SHAREGPT_KEYS = {"conversations"}
QA_PAIR_NAMES = {
    "question", "answer", "prompt", "response", "input", "output",
    "query", "reply", "text", "label",
}


def _detect_format_from_records(records: list[dict]) -> str:
    """Detect dataset format from a sample of parsed records."""
    if not records:
        return "unknown"

    keys = set(records[0].keys())

    # Alpaca: has instruction + output
    if ALPACA_KEYS.issubset(keys):
        return "alpaca"

    # ShareGPT: has conversations array with from/value or role/content
    if "conversations" in keys:
        convos = records[0]["conversations"]
        if isinstance(convos, list) and len(convos) > 0:
            first = convos[0]
            if isinstance(first, dict) and ("from" in first or "role" in first):
                return "sharegpt"

    # Simple Q&A: exactly 2 columns, both look like text pair names
    lower_keys = {k.lower() for k in keys}
    if len(keys) == 2 and lower_keys.issubset(QA_PAIR_NAMES):
        return "qa"

    # Raw text: single column
    if len(keys) == 1:
        return "raw"

    return "unknown"


def _estimate_token_length(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def _record_text_length(record: dict, fmt: str) -> int:
    """Estimate total token length of a record based on format."""
    if fmt == "alpaca":
        parts = [
            record.get("instruction", ""),
            record.get("input", ""),
            record.get("output", ""),
        ]
        return _estimate_token_length(" ".join(parts))
    elif fmt == "sharegpt":
        convos = record.get("conversations", [])
        text = " ".join(
            c.get("value", "") or c.get("content", "")
            for c in convos if isinstance(c, dict)
        )
        return _estimate_token_length(text)
    elif fmt == "qa":
        return _estimate_token_length(" ".join(str(v) for v in record.values()))
    else:
        return _estimate_token_length(" ".join(str(v) for v in record.values()))


def _record_to_preview(record: dict, fmt: str) -> DatasetPreviewRow:
    """Convert a record to a preview row."""
    if fmt == "alpaca":
        return DatasetPreviewRow(
            instruction=record.get("instruction", ""),
            input=record.get("input", ""),
            output=record.get("output", ""),
        )
    return DatasetPreviewRow(raw=record)


# ── File parsers ──

def _parse_jsonl(filepath: Path) -> list[dict]:
    """Parse JSONL file, return all records."""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _parse_json(filepath: Path) -> list[dict]:
    """Parse JSON file (array of objects or single object)."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        # Could be ShareGPT wrapper or single record
        if "data" in data and isinstance(data["data"], list):
            return [r for r in data["data"] if isinstance(r, dict)]
        return [data]
    return []


def _parse_csv(filepath: Path) -> list[dict]:
    """Parse CSV file with DictReader."""
    records = []
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(dict(row))
    return records


def _parse_parquet(filepath: Path) -> list[dict]:
    """Parse Parquet file via pandas + pyarrow."""
    import pandas as pd
    df = pd.read_parquet(filepath)
    return df.to_dict(orient="records")


def _parse_file(filepath: Path, ext: str) -> list[dict]:
    """Dispatch to the correct parser based on extension."""
    if ext == ".jsonl":
        return _parse_jsonl(filepath)
    elif ext == ".json":
        return _parse_json(filepath)
    elif ext == ".csv":
        return _parse_csv(filepath)
    elif ext == ".parquet":
        return _parse_parquet(filepath)
    raise ValueError(f"Unsupported extension: {ext}")


# ── Endpoints ──

@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(file: UploadFile):
    """Upload a dataset file, auto-detect format, return preview."""
    # Validate extension
    ext = validate_extension(file.filename or "")
    if ext is None:
        raise HTTPException(
            400,
            f"Unsupported file type. Allowed: .csv, .jsonl, .json, .parquet. "
            f"Got: '{Path(file.filename or '').suffix}'",
        )

    # Read first 1KB for content validation
    first_chunk = await file.read(1024)
    if len(first_chunk) == 0:
        raise HTTPException(400, "Uploaded file is empty.")

    valid, error_msg = validate_file_content(first_chunk, ext)
    if not valid:
        raise HTTPException(400, f"Content validation failed: {error_msg}")

    # Read rest of file, check size
    rest = await file.read()
    full_content = first_chunk + rest
    if len(full_content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            413,
            f"File too large: {len(full_content) / (1024*1024):.1f} MB "
            f"(max {MAX_UPLOAD_SIZE_BYTES / (1024*1024):.0f} MB).",
        )

    # Save to uploads dir
    dataset_id = uuid.uuid4().hex[:12]
    safe_name = f"{dataset_id}_{file.filename}"
    upload_path = UPLOADS_DIR / safe_name
    upload_path.write_bytes(full_content)

    # Parse and detect format
    try:
        records = _parse_file(upload_path, ext)
    except Exception as e:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(400, f"Failed to parse file: {e}")

    if not records:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(400, "File contains no records.")

    fmt = _detect_format_from_records(records)
    num_samples = len(records)

    # Compute avg token length
    total_tokens = sum(_record_text_length(r, fmt) for r in records)
    avg_token_length = round(total_tokens / num_samples, 1)

    # Preview first 5
    preview = [_record_to_preview(r, fmt) for r in records[:5]]

    # Store in DB
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO datasets (id, original_filename, format_detected,
               num_samples, avg_token_length, uploaded_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (dataset_id, file.filename, fmt, num_samples, avg_token_length),
        )
        await db.commit()
    finally:
        await db.close()

    return DatasetUploadResponse(
        id=dataset_id,
        original_filename=file.filename or "",
        format_detected=fmt,
        num_samples=num_samples,
        avg_token_length=avg_token_length,
        preview=preview,
        upload_path=str(upload_path),
    )


@router.get("", response_model=DatasetListResponse)
async def list_datasets():
    """List all uploaded datasets."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, original_filename, format_detected, num_samples, "
            "avg_token_length, formatted_path, uploaded_at "
            "FROM datasets ORDER BY uploaded_at DESC"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    datasets = [
        DatasetInfo(
            id=r["id"],
            original_filename=r["original_filename"],
            format_detected=r["format_detected"],
            num_samples=r["num_samples"],
            avg_token_length=r["avg_token_length"],
            formatted_path=r["formatted_path"],
            uploaded_at=r["uploaded_at"],
        )
        for r in rows
    ]
    return DatasetListResponse(datasets=datasets)


@router.post("/{dataset_id}/format", response_model=FormatResponse)
async def format_dataset_endpoint(dataset_id: str, body: FormatRequest = None):
    """Convert uploaded dataset to standardized training JSONL."""
    if body is None:
        body = FormatRequest()

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM datasets WHERE id = ?", (dataset_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if not row:
        raise HTTPException(404, f"Dataset {dataset_id} not found.")

    # Find the upload file
    upload_file = None
    for f in UPLOADS_DIR.iterdir():
        if f.name.startswith(dataset_id):
            upload_file = f
            break

    if not upload_file or not upload_file.exists():
        raise HTTPException(404, "Upload file not found on disk.")

    ext = validate_extension(row["original_filename"])
    if not ext:
        raise HTTPException(400, "Cannot determine file extension.")

    detected_format = row["format_detected"] or "unknown"

    # Build column map if provided
    col_map = None
    if body.column_mapping:
        col_map = {}
        if body.column_mapping.instruction:
            col_map["instruction"] = body.column_mapping.instruction
        if body.column_mapping.output:
            col_map["output"] = body.column_mapping.output
        if body.column_mapping.input:
            col_map["input"] = body.column_mapping.input
        if not col_map:
            col_map = None

    try:
        result = format_dataset(
            upload_path=upload_file,
            ext=ext,
            dataset_id=dataset_id,
            detected_format=detected_format,
            col_map=col_map,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("Format conversion failed")
        raise HTTPException(500, f"Format conversion failed: {e}")

    # Update DB with formatted path and refreshed stats
    db = await get_db()
    try:
        await db.execute(
            """UPDATE datasets SET formatted_path = ?, num_samples = ?,
               avg_token_length = ? WHERE id = ?""",
            (result.formatted_path, result.total_samples,
             result.avg_token_length, dataset_id),
        )
        await db.commit()
    finally:
        await db.close()

    return FormatResponse(
        dataset_id=dataset_id,
        formatted_path=result.formatted_path,
        format_used=result.format_used,
        total_samples=result.total_samples,
        avg_token_length=result.avg_token_length,
        long_sample_count=result.long_sample_count,
        empty_rows_skipped=result.empty_rows_skipped,
        warnings=result.warnings,
    )


@router.get("/{dataset_id}", response_model=DatasetUploadResponse)
async def get_dataset(dataset_id: str):
    """Get dataset details + sample preview."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM datasets WHERE id = ?", (dataset_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if not row:
        raise HTTPException(404, f"Dataset {dataset_id} not found.")

    # Find the upload file to regenerate preview
    upload_file = None
    for f in UPLOADS_DIR.iterdir():
        if f.name.startswith(dataset_id):
            upload_file = f
            break

    preview = []
    if upload_file and upload_file.exists():
        ext = validate_extension(row["original_filename"])
        if ext:
            try:
                records = _parse_file(upload_file, ext)
                fmt = row["format_detected"] or "unknown"
                preview = [_record_to_preview(r, fmt) for r in records[:5]]
            except Exception:
                pass

    return DatasetUploadResponse(
        id=row["id"],
        original_filename=row["original_filename"],
        format_detected=row["format_detected"] or "unknown",
        num_samples=row["num_samples"] or 0,
        avg_token_length=row["avg_token_length"] or 0.0,
        preview=preview,
        upload_path=str(upload_file) if upload_file else "",
    )


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str):
    """Remove dataset and its files."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, formatted_path FROM datasets WHERE id = ?", (dataset_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, f"Dataset {dataset_id} not found.")

        # Delete files
        for f in UPLOADS_DIR.iterdir():
            if f.name.startswith(dataset_id):
                f.unlink(missing_ok=True)

        if row["formatted_path"]:
            Path(row["formatted_path"]).unlink(missing_ok=True)

        await db.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        await db.commit()
    finally:
        await db.close()

    return {"deleted": dataset_id}
