"""
Auto-detect + convert datasets to training format.
Outputs standardized JSONL to data/formatted/.

For large files (>50MB), uses streaming/chunked reads.
Validates: rejects empty rows, warns on samples >2048 tokens.
"""
import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.config import FORMATTED_DIR

logger = logging.getLogger(__name__)

LARGE_FILE_THRESHOLD = 50 * 1024 * 1024  # 50 MB
TOKEN_WARN_THRESHOLD = 2048


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class FormatResult:
    formatted_path: str
    total_samples: int
    avg_token_length: float
    format_used: str
    warnings: list[str] = field(default_factory=list)
    long_sample_count: int = 0
    empty_rows_skipped: int = 0


# ── Converters: each takes a record dict and returns a standardized dict or None ──

def _convert_alpaca(record: dict) -> Optional[dict]:
    """Alpaca format — pass through, just ensure keys exist."""
    instruction = (record.get("instruction") or "").strip()
    output = (record.get("output") or "").strip()
    if not instruction and not output:
        return None
    return {
        "instruction": instruction,
        "input": (record.get("input") or "").strip(),
        "output": output,
    }


def _convert_sharegpt(record: dict) -> Optional[dict]:
    """ShareGPT format — normalize from/value to role/content."""
    convos = record.get("conversations", [])
    if not isinstance(convos, list) or len(convos) == 0:
        return None
    normalized = []
    for turn in convos:
        if not isinstance(turn, dict):
            continue
        # Handle both from/value and role/content variants
        role = turn.get("role") or turn.get("from", "")
        content = turn.get("content") or turn.get("value", "")
        if not role or not content:
            continue
        # Normalize role names
        role = role.lower().strip()
        if role in ("human", "user"):
            role = "user"
        elif role in ("gpt", "assistant", "bot"):
            role = "assistant"
        elif role == "system":
            role = "system"
        else:
            role = "user"  # default unknown roles to user
        normalized.append({"role": role, "content": content.strip()})
    if not normalized:
        return None
    return {"conversations": normalized}


def _convert_qa(record: dict, col_map: Optional[dict] = None) -> Optional[dict]:
    """Simple Q&A — map two columns to instruction/output."""
    if col_map:
        instruction_col = col_map.get("instruction", "")
        output_col = col_map.get("output", "")
    else:
        # Auto-detect: first column → instruction, second → output
        keys = list(record.keys())
        # Try to match known names
        instruction_col = None
        output_col = None
        for k in keys:
            kl = k.lower()
            if kl in ("instruction", "question", "prompt", "input", "query", "text"):
                instruction_col = k
            elif kl in ("output", "answer", "response", "reply", "label"):
                output_col = k
        # Fallback: just use positional
        if not instruction_col:
            instruction_col = keys[0]
        if not output_col:
            output_col = keys[1] if len(keys) > 1 else keys[0]

    instruction = str(record.get(instruction_col, "")).strip()
    output = str(record.get(output_col, "")).strip()
    if not instruction and not output:
        return None
    return {
        "instruction": instruction,
        "input": "",
        "output": output,
    }


def _convert_raw(record: dict) -> Optional[dict]:
    """Raw text — single column → completion format."""
    values = list(record.values())
    text = str(values[0]).strip() if values else ""
    if not text:
        return None
    return {
        "instruction": text,
        "input": "",
        "output": "",
    }


def _convert_unknown(record: dict, col_map: Optional[dict] = None) -> Optional[dict]:
    """Unknown format — use column mapping if provided, else concatenate all fields."""
    if col_map:
        return _convert_qa(record, col_map)
    # Fallback: dump all values as instruction
    text = " | ".join(f"{k}: {v}" for k, v in record.items() if v)
    if not text:
        return None
    return {
        "instruction": text,
        "input": "",
        "output": "",
    }


# ── Streaming parsers for large files ──

def _iter_jsonl(filepath: Path):
    """Yield records one at a time from a JSONL file."""
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _iter_json(filepath: Path):
    """Load JSON file — for arrays, yield each element."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict):
                yield r
    elif isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            for r in data["data"]:
                if isinstance(r, dict):
                    yield r
        else:
            yield data


def _iter_csv(filepath: Path):
    """Yield records one at a time from a CSV file."""
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield dict(row)


def _iter_parquet(filepath: Path):
    """Yield records from a Parquet file in chunks."""
    import pandas as pd
    file_size = filepath.stat().st_size
    if file_size > LARGE_FILE_THRESHOLD:
        # Read in chunks
        pf = pd.read_parquet(filepath)
        chunk_size = 1000
        for start in range(0, len(pf), chunk_size):
            chunk = pf.iloc[start:start + chunk_size]
            for record in chunk.to_dict(orient="records"):
                yield record
    else:
        df = pd.read_parquet(filepath)
        for record in df.to_dict(orient="records"):
            yield record


def _iter_file(filepath: Path, ext: str):
    """Dispatch to the correct streaming parser."""
    if ext == ".jsonl":
        return _iter_jsonl(filepath)
    elif ext == ".json":
        return _iter_json(filepath)
    elif ext == ".csv":
        return _iter_csv(filepath)
    elif ext == ".parquet":
        return _iter_parquet(filepath)
    raise ValueError(f"Unsupported extension: {ext}")


# ── Main formatting function ──

def format_dataset(
    upload_path: Path,
    ext: str,
    dataset_id: str,
    detected_format: str,
    col_map: Optional[dict] = None,
) -> FormatResult:
    """
    Convert an uploaded dataset to standardized training JSONL.

    Args:
        upload_path: Path to the raw uploaded file.
        ext: File extension (.csv, .jsonl, .json, .parquet).
        dataset_id: Unique dataset ID for naming the output.
        detected_format: Format detected during upload (alpaca/sharegpt/qa/raw/unknown).
        col_map: Optional column mapping for unknown formats.
                 e.g. {"instruction": "question_col", "output": "answer_col"}

    Returns:
        FormatResult with path, stats, and warnings.
    """
    output_path = FORMATTED_DIR / f"{dataset_id}.jsonl"
    warnings = []
    total_samples = 0
    total_tokens = 0
    long_samples = 0
    empty_skipped = 0

    # Pick converter
    fmt = detected_format
    if col_map and fmt in ("unknown", "qa"):
        # Column mapping overrides auto-detection for these formats
        pass

    with open(output_path, "w", encoding="utf-8") as out_f:
        for record in _iter_file(upload_path, ext):
            # Convert based on format
            if fmt == "alpaca":
                converted = _convert_alpaca(record)
            elif fmt == "sharegpt":
                converted = _convert_sharegpt(record)
            elif fmt == "qa":
                converted = _convert_qa(record, col_map)
            elif fmt == "raw":
                converted = _convert_raw(record)
            else:
                converted = _convert_unknown(record, col_map)

            if converted is None:
                empty_skipped += 1
                continue

            # Estimate token length for the converted record
            if "conversations" in converted:
                text = " ".join(c["content"] for c in converted["conversations"])
            else:
                text = " ".join(str(v) for v in converted.values())
            tokens = _estimate_tokens(text)
            total_tokens += tokens

            if tokens > TOKEN_WARN_THRESHOLD:
                long_samples += 1

            out_f.write(json.dumps(converted, ensure_ascii=False) + "\n")
            total_samples += 1

    if total_samples == 0:
        output_path.unlink(missing_ok=True)
        raise ValueError("No valid samples after conversion. All rows were empty or invalid.")

    avg_tokens = round(total_tokens / total_samples, 1)

    if empty_skipped > 0:
        warnings.append(f"Skipped {empty_skipped} empty/invalid rows.")
    if long_samples > 0:
        warnings.append(
            f"{long_samples} samples exceed {TOKEN_WARN_THRESHOLD} tokens "
            f"(may be truncated during training)."
        )

    return FormatResult(
        formatted_path=str(output_path),
        total_samples=total_samples,
        avg_token_length=avg_tokens,
        format_used=fmt,
        warnings=warnings,
        long_sample_count=long_samples,
        empty_rows_skipped=empty_skipped,
    )
