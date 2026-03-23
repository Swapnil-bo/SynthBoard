"""Pydantic schemas for training endpoints."""
from typing import Optional
from pydantic import BaseModel, Field

from backend.config import TRAINING_DEFAULTS, QLORA_DEFAULTS


class TrainingRequest(BaseModel):
    """Request to start a fine-tuning run."""
    model_name: str = Field(
        ...,
        description="HuggingFace model ID, e.g. 'unsloth/Qwen2.5-1.5B-bnb-4bit'",
    )
    dataset_id: str = Field(
        ...,
        description="ID of a formatted dataset in the DB",
    )
    # QLoRA overrides (all optional, defaults from config)
    r: int = QLORA_DEFAULTS["r"]
    lora_alpha: int = QLORA_DEFAULTS["lora_alpha"]
    lora_dropout: float = QLORA_DEFAULTS["lora_dropout"]

    # Training overrides (all optional, defaults from config)
    num_train_epochs: int = TRAINING_DEFAULTS["num_train_epochs"]
    learning_rate: float = TRAINING_DEFAULTS["learning_rate"]
    per_device_train_batch_size: int = TRAINING_DEFAULTS["per_device_train_batch_size"]
    gradient_accumulation_steps: int = TRAINING_DEFAULTS["gradient_accumulation_steps"]
    max_seq_length: int = TRAINING_DEFAULTS["max_seq_length"]
    warmup_ratio: float = TRAINING_DEFAULTS["warmup_ratio"]
    logging_steps: int = TRAINING_DEFAULTS["logging_steps"]
    save_steps: int = TRAINING_DEFAULTS["save_steps"]

    # Optional: override max_steps (0 = use epochs)
    max_steps: int = 0


class TrainingRunResponse(BaseModel):
    """Response for a training run record."""
    id: str
    base_model: str
    dataset_id: str
    config: dict
    status: str
    final_loss: Optional[float] = None
    total_steps: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    checkpoint_path: Optional[str] = None
    gguf_path: Optional[str] = None
    ollama_model_name: Optional[str] = None


class TrainingProgress(BaseModel):
    """A single SSE progress event during training."""
    step: int
    total_steps: int
    loss: Optional[float] = None
    learning_rate: Optional[float] = None
    vram_used_mb: Optional[int] = None
    eta_seconds: Optional[float] = None
