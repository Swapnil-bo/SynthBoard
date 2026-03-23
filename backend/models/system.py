"""Pydantic schemas for system endpoints."""
from typing import Optional
from pydantic import BaseModel


class GpuStatsResponse(BaseModel):
    available: bool
    backend: Optional[str] = None
    name: Optional[str] = None
    vram_total_mb: Optional[int] = None
    vram_used_mb: Optional[int] = None
    vram_free_mb: Optional[int] = None
    gpu_utilization_pct: Optional[int] = None
    temperature_c: Optional[int] = None
    driver_version: Optional[str] = None
    warning: Optional[str] = None


class DiskCategory(BaseModel):
    path: str
    size_mb: float
    file_count: int


class DiskUsageResponse(BaseModel):
    uploads: DiskCategory
    formatted: DiskCategory
    checkpoints: DiskCategory
    exports: DiskCategory
    database_mb: float
    total_mb: float


class HealthResponse(BaseModel):
    status: str  # "ok" or "degraded"
    ollama_running: bool
    ollama_url: str
    gpu_available: bool
    training_active: bool
    active_training_run_id: Optional[str] = None
    disk_free_mb: float
    database_ok: bool
    warnings: list[str] = []


class ModelTierInfo(BaseModel):
    model_id: str
    tier: int
    params: str
    vram_train_mb: int
    family: str
    gated: bool


class CapabilitiesResponse(BaseModel):
    # CUDA / torch
    cuda_available: bool
    cuda_version: Optional[str] = None
    torch_version: Optional[str] = None
    gpu_name: Optional[str] = None
    vram_total_mb: Optional[int] = None

    # Core dependencies
    unsloth_available: bool
    unsloth_version: Optional[str] = None
    bitsandbytes_available: bool
    bitsandbytes_version: Optional[str] = None
    trl_available: bool
    trl_version: Optional[str] = None

    # GGUF export
    gguf_export_method: str  # unsloth-native / llama-cpp-python / external-binary / unavailable

    # Available models for fine-tuning on this hardware
    available_model_tiers: list[ModelTierInfo]

    # Training readiness
    training_ready: bool

    warnings: list[str] = []
