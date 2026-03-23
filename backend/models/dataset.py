"""Pydantic schemas for datasets."""
from typing import Any, Optional
from pydantic import BaseModel


class DatasetPreviewRow(BaseModel):
    """A single row from the dataset preview."""
    instruction: Optional[str] = None
    input: Optional[str] = None
    output: Optional[str] = None
    # For non-alpaca formats, store raw keys
    raw: Optional[dict[str, Any]] = None


class DatasetUploadResponse(BaseModel):
    id: str
    original_filename: str
    format_detected: str  # alpaca, sharegpt, qa, raw, unknown
    num_samples: int
    avg_token_length: float
    preview: list[DatasetPreviewRow]
    upload_path: str


class DatasetInfo(BaseModel):
    id: str
    original_filename: str
    format_detected: Optional[str] = None
    num_samples: Optional[int] = None
    avg_token_length: Optional[float] = None
    formatted_path: Optional[str] = None
    uploaded_at: Optional[str] = None


class DatasetListResponse(BaseModel):
    datasets: list[DatasetInfo]


class ColumnMapping(BaseModel):
    """Optional column mapping for unknown/qa formats."""
    instruction: Optional[str] = None
    output: Optional[str] = None
    input: Optional[str] = None


class FormatRequest(BaseModel):
    """Request body for format conversion."""
    column_mapping: Optional[ColumnMapping] = None


class FormatResponse(BaseModel):
    dataset_id: str
    formatted_path: str
    format_used: str
    total_samples: int
    avg_token_length: float
    long_sample_count: int
    empty_rows_skipped: int
    warnings: list[str]
