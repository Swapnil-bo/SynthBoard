"""
SynthBoard configuration — all paths, constants, hardware limits.
Loads .env via python-dotenv.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
UPLOADS_DIR = DATA_DIR / "uploads"
FORMATTED_DIR = DATA_DIR / "formatted"
CHECKPOINTS_DIR = DATA_DIR / "checkpoints"
EXPORTS_DIR = DATA_DIR / "exports"
DEMO_DIR = DATA_DIR / "demo"
PROMPT_BANK_PATH = DATA_DIR / "prompt_bank.json"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "synthboard.db")))
TRAINING_LOG_DIR = Path(os.getenv("TRAINING_LOG_DIR", str(PROJECT_ROOT / "logs")))

# Ensure data dirs exist
for _d in (UPLOADS_DIR, FORMATTED_DIR, CHECKPOINTS_DIR, EXPORTS_DIR, TRAINING_LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Upload limits
# ---------------------------------------------------------------------------
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "500"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ---------------------------------------------------------------------------
# HuggingFace
# ---------------------------------------------------------------------------
HF_TOKEN = os.getenv("HF_TOKEN", "")

# Models that require HF_TOKEN + license acceptance on huggingface.co
GATED_MODELS = [
    "meta-llama/Llama-3.2-1B",
    "meta-llama/Llama-3.2-1B-Instruct",
    "meta-llama/Llama-3.2-3B",
    "meta-llama/Llama-3.2-3B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "unsloth/Llama-3.2-1B-bnb-4bit",
    "unsloth/Llama-3.2-1B-Instruct-bnb-4bit",
    "unsloth/Llama-3.2-3B-bnb-4bit",
    "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
]

# ---------------------------------------------------------------------------
# Hardware limits (RTX 3050 6GB, 8GB RAM)
# ---------------------------------------------------------------------------
VRAM_TOTAL_MB = 6144
VRAM_SAFETY_MARGIN_MB = int(os.getenv("VRAM_SAFETY_MARGIN_MB", "500"))
DEFAULT_MAX_SEQ_LENGTH = int(os.getenv("DEFAULT_MAX_SEQ_LENGTH", "1024"))

# ---------------------------------------------------------------------------
# QLoRA defaults (tuned for 6GB VRAM)
# ---------------------------------------------------------------------------
QLORA_DEFAULTS = {
    "r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.05,
    "target_modules": [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    "bias": "none",
    "load_in_4bit": True,
    "bnb_4bit_compute_dtype": "float16",
    "bnb_4bit_quant_type": "nf4",
}

TRAINING_DEFAULTS = {
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 16,
    "num_train_epochs": 3,
    "learning_rate": 2e-4,
    "warmup_ratio": 0.05,
    "lr_scheduler_type": "cosine",
    "max_seq_length": DEFAULT_MAX_SEQ_LENGTH,
    "logging_steps": 5,
    "save_steps": 50,
    "fp16": True,
    "optim": "adamw_8bit",
    "gradient_checkpointing": True,
    "dataloader_num_workers": 0,       # 0 on Windows to avoid multiprocessing issues
    "dataloader_pin_memory": False,    # False to save RAM on 8GB system
}
