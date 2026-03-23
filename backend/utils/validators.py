"""Dataset validation — content-based, not just extension."""
import csv
import io
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".jsonl", ".json", ".parquet"}


def validate_extension(filename: str) -> Optional[str]:
    """Return the lowercase extension if allowed, else None."""
    ext = Path(filename).suffix.lower()
    return ext if ext in ALLOWED_EXTENSIONS else None


def _looks_binary(chunk: bytes) -> bool:
    """Heuristic: if >10% of bytes are non-text control chars, it's binary."""
    if not chunk:
        return True
    control = sum(1 for b in chunk if b < 0x09 or (0x0E <= b <= 0x1F))
    return (control / len(chunk)) > 0.10


def validate_csv_content(chunk: bytes) -> bool:
    """Try to parse the first chunk as CSV. Returns True if valid."""
    if _looks_binary(chunk):
        return False
    try:
        text = chunk.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) >= 3:
                break
        # Need at least a header + 1 data row, and consistent column count
        if len(rows) < 2:
            return False
        col_count = len(rows[0])
        return col_count >= 1 and all(len(r) == col_count for r in rows)
    except Exception:
        return False


def validate_json_content(chunk: bytes) -> bool:
    """Try to parse as JSON array or object."""
    if _looks_binary(chunk):
        return False
    try:
        text = chunk.decode("utf-8", errors="replace").strip()
        if not text.startswith(("{", "[")):
            return False
        json.loads(text)
        return True
    except json.JSONDecodeError:
        # Might be truncated — check if it at least starts valid
        return text.startswith("[") or text.startswith("{")


def validate_jsonl_content(chunk: bytes) -> bool:
    """Try to parse first few lines as JSONL. Last line may be truncated by the
    1KB read boundary, so exclude it from strict validation."""
    if _looks_binary(chunk):
        return False
    try:
        text = chunk.decode("utf-8", errors="replace")
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return False
        # Drop the last line — it may be truncated at the chunk boundary
        complete_lines = lines[:-1] if len(lines) > 1 else lines
        parsed = 0
        for line in complete_lines[:5]:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                return False
            parsed += 1
        return parsed >= 1
    except (json.JSONDecodeError, ValueError):
        return False


def validate_parquet_content(chunk: bytes) -> bool:
    """Parquet files start with magic bytes PAR1."""
    return chunk[:4] == b"PAR1"


def validate_file_content(chunk: bytes, ext: str) -> tuple[bool, str]:
    """
    Validate file content matches its extension.
    Returns (is_valid, error_message).
    """
    if ext == ".csv":
        if validate_csv_content(chunk):
            return True, ""
        return False, "File content is not valid CSV (binary data or malformed)."
    elif ext == ".jsonl":
        if validate_jsonl_content(chunk):
            return True, ""
        return False, "File content is not valid JSONL (expected one JSON object per line)."
    elif ext == ".json":
        if validate_json_content(chunk):
            return True, ""
        return False, "File content is not valid JSON."
    elif ext == ".parquet":
        if validate_parquet_content(chunk):
            return True, ""
        return False, "File does not have valid Parquet magic bytes (PAR1)."
    return False, f"Unsupported extension: {ext}"
