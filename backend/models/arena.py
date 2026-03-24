"""Pydantic schemas for models and arena endpoints."""
from typing import Optional
from pydantic import BaseModel, Field


class ArenaModelResponse(BaseModel):
    """Response for an arena model record."""
    id: str
    name: str
    ollama_name: str
    source: str  # 'base' or 'fine-tuned'
    training_run_id: Optional[str] = None
    elo_rating: float = 1200.0
    total_battles: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_ties: int = 0
    avg_ttft_ms: Optional[float] = None
    avg_tps: Optional[float] = None
    registered_at: Optional[str] = None


class RegisterBaseModelRequest(BaseModel):
    """Request to register a base Ollama model for arena."""
    name: str = Field(..., description="Display name for the model")
    ollama_name: str = Field(..., description="Ollama model tag (e.g. 'qwen2.5:1.5b')")


class ExportRequest(BaseModel):
    """Optional overrides for GGUF export."""
    quantization_method: str = Field(
        default="q4_k_m",
        description="GGUF quantization method (q4_k_m, q5_k_m, q8_0, etc.)",
    )


class ExportResponse(BaseModel):
    """Response for a GGUF export operation."""
    success: bool
    run_id: str
    gguf_path: Optional[str] = None
    ollama_model_name: Optional[str] = None
    arena_model_id: Optional[str] = None
    error: Optional[str] = None
    total_time_seconds: Optional[float] = None
