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


# ---------------------------------------------------------------------------
# Arena battle schemas
# ---------------------------------------------------------------------------

class BattleRequest(BaseModel):
    """Request to start a new arena battle."""
    prompt: Optional[str] = Field(
        None,
        description="Custom prompt. If omitted, a random prompt is picked from the bank.",
    )


class BattleResponse(BaseModel):
    """Response for a battle — blinded (model identities hidden until vote)."""
    id: str
    prompt: str
    prompt_category: Optional[str] = None
    response_a: str
    response_b: str
    model_a_ttft_ms: Optional[float] = None
    model_b_ttft_ms: Optional[float] = None
    model_a_total_ms: Optional[float] = None
    model_b_total_ms: Optional[float] = None
    model_a_tokens: Optional[int] = None
    model_b_tokens: Optional[int] = None


class VoteRequest(BaseModel):
    """Request to submit a vote on a battle."""
    winner: str = Field(
        ...,
        description="Vote: 'a', 'b', 'tie', or 'skip'.",
        pattern="^(a|b|tie|skip)$",
    )


class VoteResponse(BaseModel):
    """Response after voting — reveals model identities and Elo changes."""
    battle_id: str
    winner: str
    model_a_name: str
    model_b_name: str
    model_a_id: str
    model_b_id: str
    model_a_elo_before: float
    model_b_elo_before: float
    model_a_elo_after: float
    model_b_elo_after: float


class BattleDetailResponse(BaseModel):
    """Full battle details (reveals models after vote, or hides if not voted)."""
    id: str
    prompt: str
    prompt_category: Optional[str] = None
    response_a: str
    response_b: str
    model_a_ttft_ms: Optional[float] = None
    model_b_ttft_ms: Optional[float] = None
    model_a_total_ms: Optional[float] = None
    model_b_total_ms: Optional[float] = None
    model_a_tokens: Optional[int] = None
    model_b_tokens: Optional[int] = None
    winner: Optional[str] = None
    # Revealed after vote
    model_a_name: Optional[str] = None
    model_b_name: Optional[str] = None
    model_a_id: Optional[str] = None
    model_b_id: Optional[str] = None
    model_a_elo_before: Optional[float] = None
    model_b_elo_before: Optional[float] = None
    model_a_elo_after: Optional[float] = None
    model_b_elo_after: Optional[float] = None
    voted_at: Optional[str] = None
    created_at: Optional[str] = None


class BattleHistoryResponse(BaseModel):
    """Paginated battle history."""
    battles: list[BattleDetailResponse]
    total: int
    page: int
    page_size: int
