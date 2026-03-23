# CLAUDE.md — SynthBoard: Local Fine-Tuning Pipeline + Model Arena

## Project Identity

SynthBoard is a local-first platform that lets you upload a dataset, auto-format it for fine-tuning, QLoRA fine-tune a model on consumer hardware, export it, and pit it against base models in a blind side-by-side arena with Elo ratings. The entire lifecycle — data prep → training → deployment → evaluation — runs on a single RTX 3050 6GB.

---

## Hardware Constraints (NON-NEGOTIABLE)

- **GPU**: NVIDIA RTX 3050, 6GB VRAM — this is the ceiling. Every component must respect it.
- **RAM**: 8GB DDR4 — dataset processing must stream/chunk. No loading full datasets into memory.
- **OS**: Windows 11. **If Step 0 passes natively** → terminal is **cmd** (use `&&` chaining, NOT PowerShell syntax). **If Step 0 fails natively** → WSL2 (Ubuntu 22.04) for the backend, cmd for git/frontend only. The build order adapts based on Step 0 outcome.
- **Disk**: Assume ≥50GB free. Fine-tuned checkpoints + GGUF exports will eat space; implement cleanup utilities.

### VRAM Budget (hard limits, measured not guessed)

| Operation | Max VRAM | Notes |
|---|---|---|
| QLoRA fine-tune (≤1.5B params, unsloth, 4-bit) | ~3.0-3.5 GB | Safe. Batch size 1-2, gradient accumulation 8-16. |
| QLoRA fine-tune (≤3B params, unsloth, 4-bit) | ~4.5-5.5 GB | Tight. Batch size 1 only, gradient accumulation 16+. Monitor with nvidia-smi. |
| QLoRA fine-tune (7B params) | ❌ OOM | Do NOT attempt. Will crash or thrash. |
| Ollama inference (1.5B Q4_K_M GGUF) | ~1.2-1.5 GB | Comfortable for arena. |
| Ollama inference (3B Q4_K_M GGUF) | ~2.0-2.8 GB | Fine for single model. Two simultaneous = tight. |
| Ollama inference (7B Q4_K_M GGUF) | ~4.5 GB | Only one at a time. No arena dual-load. |
| Arena dual-inference (two 3B models) | ~5.0-5.5 GB | Possible if sequential, NOT parallel. |

### Critical Rule: Arena Inference is SEQUENTIAL, Not Parallel

When comparing two models in the arena, send prompt to Model A → get response → unload → send prompt to Model B → get response. NEVER load two models simultaneously for 3B+. For ≤1.5B models, parallel is safe.

Implement a model loading queue in the backend:
```
POST /arena/battle → load model_a via Ollama keep_alive → generate → set keep_alive=0 → load model_b → generate → return both
```

---

## Architecture

```
synthboard/
├── backend/                    # FastAPI + Python
│   ├── main.py                 # FastAPI app entry, CORS, lifespan
│   ├── config.py               # All paths, constants, hardware limits. Must include GATED_MODELS list and MODEL_TEMPLATES dict.
│   ├── routers/
│   │   ├── datasets.py         # Upload, validate, preview, format conversion
│   │   ├── training.py         # Fine-tune launch, progress SSE, cancel, logs
│   │   ├── models.py           # List models, export GGUF, register in Ollama
│   │   ├── arena.py            # Battle generation, vote submission, Elo calc
│   │   └── system.py           # GPU stats, disk usage, health check
│   ├── services/
│   │   ├── dataset_formatter.py    # Auto-detect + convert to training format
│   │   ├── training_engine.py      # unsloth QLoRA orchestration
│   │   ├── gguf_exporter.py        # Checkpoint → GGUF → Ollama registration
│   │   ├── model_manager.py        # Ollama lifecycle (load/unload/list)
│   │   ├── arena_engine.py         # Sequential inference, battle logic
│   │   └── elo_calculator.py       # Elo rating math + persistence
│   ├── models/                 # Pydantic schemas
│   │   ├── dataset.py
│   │   ├── training.py
│   │   ├── arena.py
│   │   └── system.py
│   ├── db/
│   │   └── database.py         # SQLite via aiosqlite — battles, votes, Elo, training runs
│   └── utils/
│       ├── gpu_monitor.py      # GPU monitoring with fallback chain: pynvml → nvidia-smi CLI → null (with warning). On WSL2, pynvml needs libnvidia-ml.so — fall back to nvidia-smi.exe via /mnt/c/Windows/System32/nvidia-smi.exe. On native Windows, nvidia-smi.exe may be in C:\Windows\System32\ — use full path as fallback if not in PATH.
│       └── validators.py       # Dataset validation, size checks
├── frontend/                   # React + Vite
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── pages/
│   │   │   ├── DatasetsPage.jsx      # Upload, preview, format
│   │   │   ├── TrainingPage.jsx      # Configure + monitor fine-tune
│   │   │   ├── ModelsPage.jsx        # Model registry + export
│   │   │   ├── ArenaPage.jsx         # Side-by-side blind battle
│   │   │   └── LeaderboardPage.jsx   # Elo rankings, stats, latency
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.jsx
│   │   │   │   └── TopBar.jsx
│   │   │   ├── dataset/
│   │   │   │   ├── UploadZone.jsx
│   │   │   │   ├── DataPreview.jsx
│   │   │   │   └── FormatSelector.jsx
│   │   │   ├── training/
│   │   │   │   ├── TrainingConfig.jsx
│   │   │   │   ├── TrainingProgress.jsx  # Real-time loss curve via SSE
│   │   │   │   └── GpuMonitor.jsx
│   │   │   ├── arena/
│   │   │   │   ├── BattleView.jsx        # Two response panels, blind labels
│   │   │   │   ├── VoteButtons.jsx
│   │   │   │   └── ResponsePanel.jsx     # Streaming text + latency badge
│   │   │   └── leaderboard/
│   │   │       ├── EloTable.jsx
│   │   │       ├── WinRateChart.jsx
│   │   │       └── LatencyChart.jsx
│   │   ├── hooks/
│   │   │   ├── useSSE.js           # Server-Sent Events for training progress. MUST implement exponential backoff reconnect (1s → 2s → 4s → 8s → 16s cap) on disconnect. Without this, sleep/wake or network blips silently kill the training dashboard.
│   │   │   ├── useArena.js         # Battle state management
│   │   │   └── useGpuStats.js      # Polling GPU metrics
│   │   └── lib/
│   │       ├── api.js              # Axios instance + endpoints
│   │       └── constants.js
│   ├── index.html
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── package.json
├── data/
│   ├── uploads/                # Raw uploaded datasets
│   ├── formatted/              # Training-ready datasets
│   ├── checkpoints/            # QLoRA adapter checkpoints
│   ├── exports/                # GGUF files
│   ├── demo/                   # Demo dataset for quick testing
│   │   └── alpaca_demo_100.jsonl
│   └── prompt_bank.json        # Arena evaluation prompts (30 diverse, categorized)
├── synthboard.db               # SQLite database
├── requirements.txt
├── .gitignore
├── .env.example
└── README.md
```

---

## Tech Stack

### Backend
- **FastAPI** — async REST API + SSE streaming
- **unsloth** — QLoRA fine-tuning (2-4x faster, 60-70% less VRAM vs vanilla PEFT)
- **trl** — `SFTTrainer` for supervised fine-tuning (this is the actual trainer class, unsloth wraps around it)
- **transformers + peft + bitsandbytes** — model loading, QLoRA config (unsloth wraps these)
- **Ollama** — model serving for arena inference (must be installed separately)
- **httpx** — async HTTP client for Ollama API calls in the arena engine
- **aiosqlite** — async SQLite for Elo ratings, battle history, training logs
- **pandas** — dataset preview/validation (chunked reads only, never full load for large files)
- **pyarrow** — required for `.parquet` file reading (pandas alone can't read parquet without this)
- **python-multipart** — file uploads
- **python-dotenv** — load `.env` file into environment (config.py depends on this)
- **psutil + pynvml** — system/GPU monitoring

### Frontend
- **React 18 + Vite** — SPA
- **Tailwind CSS** — styling
- **Recharts** — loss curves, Elo history, latency distributions
- **react-router-dom v6** — page navigation
- **react-dropzone** — file upload UX
- **axios** — API calls

### Infrastructure
- **Ollama** — local model serving (user must have it installed)
- **SQLite** — zero-config persistence
- **SSE (EventSource)** — real-time training progress streaming

---

## Supported Model Families (Validated for 6GB VRAM + unsloth)

### Tier 1 — Comfortable (recommended default)
- **Qwen2.5-1.5B / Qwen2.5-1.5B-Instruct**
- **SmolLM2-1.7B / SmolLM2-1.7B-Instruct**
- **Llama-3.2-1B** (limited but fast)
- **Phi-3.5-mini (3.8B)** — borderline, test before offering

### Tier 2 — Tight but Possible (advanced users, monitor VRAM)
- **Qwen2.5-3B / Qwen2.5-3B-Instruct**
- **Llama-3.2-3B / Llama-3.2-3B-Instruct**
- **Phi-3-mini-4k (3.8B)**

### Tier 3 — Arena Inference Only (too large for fine-tuning on this hardware)
- **Mistral-7B-Instruct-v0.3** — serve via Ollama GGUF Q4 only
- **Llama-3.1-8B-Instruct** — serve via Ollama GGUF Q4 only
- **Qwen2.5-7B-Instruct** — serve via Ollama GGUF Q4 only

The UI must clearly label tiers and show estimated VRAM per model. Gray out / warn on Tier 2+.

---

## Dataset Format Pipeline

### Accepted Upload Formats
- `.csv` — columns auto-detected
- `.jsonl` — one JSON object per line
- `.json` — array of objects or ShareGPT format
- `.parquet` — for HuggingFace dataset exports

### Auto-Detection Logic (dataset_formatter.py)
1. **Alpaca format**: detect keys `instruction`, `input`, `output` → ready as-is
2. **ShareGPT format**: detect key `conversations` with `from`/`value` pairs → convert to chat template
3. **Simple Q&A**: detect two columns (any names like `question`/`answer`, `prompt`/`response`, `input`/`output`) → convert to Alpaca
4. **Raw text**: single column of text → format as completion-style (no instruction tuning)
5. **Unknown**: show column preview in UI, let user manually map columns to `instruction`/`input`/`output`

### Conversion Output
All datasets get converted to a standardized JSONL with this schema:
```json
{"instruction": "...", "input": "...", "output": "..."}
```
Or for chat format:
```json
{"conversations": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

The formatter must:
- Stream-read large files (never pd.read_csv() without chunking for files >50MB)
- Validate: reject empty rows, warn on extremely long samples (>2048 tokens)
- Show a preview of first 5 converted samples in the UI before training
- Report stats: total samples, avg token length, estimated training time

---

## Fine-Tuning Engine (training_engine.py)

### QLoRA Configuration Defaults (tuned for 6GB VRAM)

```python
QLORA_DEFAULTS = {
    "r": 16,                        # LoRA rank — 16 is sweet spot for small models
    "lora_alpha": 32,               # alpha = 2*r is standard
    "lora_dropout": 0.05,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
    "bias": "none",
    "load_in_4bit": True,           # MANDATORY for 6GB VRAM
    "bnb_4bit_compute_dtype": "float16",
    "bnb_4bit_quant_type": "nf4",
}

TRAINING_DEFAULTS = {
    "per_device_train_batch_size": 1,       # DO NOT increase on 8GB RAM
    "gradient_accumulation_steps": 16,       # Effective batch = 16
    "num_train_epochs": 3,
    "learning_rate": 2e-4,
    "warmup_ratio": 0.05,
    "lr_scheduler_type": "cosine",
    "max_seq_length": 1024,                  # Cap at 1024 for VRAM safety
    "logging_steps": 5,
    "save_steps": 50,
    "fp16": True,                            # Use fp16 on 3050 (no bf16 on Ampere-lite)
    "optim": "adamw_8bit",                   # 8-bit optimizer saves RAM
    "gradient_checkpointing": True,          # MANDATORY — trades compute for VRAM
    "dataloader_num_workers": 0,             # 0 on Windows to avoid multiprocessing issues
    "dataloader_pin_memory": False,          # False to save RAM on 8GB system
}
```

### CRITICAL: Training Must Run in a Background Thread

`SFTTrainer.train()` is synchronous and blocking. FastAPI is async. If you call `trainer.train()` directly in a route handler, the entire server freezes — the SSE endpoint will emit nothing until training finishes. **This is the #1 runtime bug to prevent.**

Pattern:
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

training_executor = ThreadPoolExecutor(max_workers=1)  # Only 1 — VRAM can't handle concurrent training

async def start_training(run_id: str, config: dict):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(training_executor, _run_training_sync, run_id, config)
```

The SSE queue pattern works ONLY because training runs in a separate thread. The `TrainerCallback` pushes events to a `queue.Queue()` from the training thread, and the SSE endpoint reads from it in the async event loop.

### Global Training Lock

**Only one training run may execute at a time.** On 6GB VRAM, two concurrent training jobs = instant OOM. Enforce this at the API level:

```python
# In training router
@router.post("/api/training/start")
async def start_training(request: TrainingRequest):
    running = await db.fetch_one("SELECT id FROM training_runs WHERE status = 'running'")
    if running:
        raise HTTPException(409, f"Training run {running['id']} is already active. Cancel it first.")
    # ... proceed with training
```

### Total Steps Pre-Computation

Before training starts, compute and store `total_steps` in the DB:
```python
total_steps = math.ceil(len(dataset) / batch_size / gradient_accumulation_steps) * num_epochs
```
This is required for ETA calculation in the SSE stream. Without it, `eta_seconds` has no denominator.

### VRAM Guard
Before launching any training run:
1. Check the global training lock (reject if another run is active)
2. Query `nvidia-smi` for free VRAM
3. Estimate required VRAM based on model size + config
4. If estimated > (free_vram - 500MB safety margin) → BLOCK with clear error message
5. During training, poll VRAM every 10 seconds. If >95% usage, log a warning to the SSE stream.

### Training Progress (SSE stream)

**Disconnect handling (prevents memory leak)**: If the user closes the browser mid-training, the SSE queue keeps filling with no reader. The SSE endpoint must:
1. Check `await request.is_disconnected()` on every iteration
2. When disconnected, set a flag that the training callback checks
3. The callback stops pushing events if no active readers exist
4. Use a bounded `queue.Queue(maxsize=100)` so it drops old events if the reader falls behind, rather than growing unbounded

**Multiple tabs support**: Use a broadcast pattern (list of queues), not a single consume-once queue. Each SSE subscriber gets its own queue. The training callback pushes to all registered queues.

Emit events:
```
event: progress
data: {"step": 42, "total_steps": 300, "loss": 1.234, "lr": 0.00018, "vram_used_mb": 4800, "eta_seconds": 540}

event: checkpoint
data: {"step": 50, "path": "data/checkpoints/run_abc123/checkpoint-50"}

event: complete
data: {"final_loss": 0.45, "total_time_seconds": 1820, "checkpoint_path": "..."}

event: error
data: {"message": "CUDA out of memory. Reduce max_seq_length or use a smaller model."}
```

### unsloth Integration Pattern
```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-1.5B-bnb-4bit",   # Use unsloth's pre-quantized
    max_seq_length=1024,
    load_in_4bit=True,
    dtype=None,  # auto-detect
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                     "gate_proj", "up_proj", "down_proj"],
    bias="none",
    use_gradient_checkpointing="unsloth",  # unsloth's optimized version
)
```

**IMPORTANT**: unsloth must be installed via their specific instructions for Windows + CUDA. Pin the version. Do NOT just `pip install unsloth` — check their GitHub for the correct install command for the user's CUDA version.

---

## GGUF Export Pipeline (gguf_exporter.py)

After fine-tuning completes:

1. **Merge LoRA adapters** into base model:
   ```python
   model.save_pretrained_merged("data/exports/merged_model", tokenizer)
   ```
2. **Convert to GGUF** using llama.cpp's `convert_hf_to_gguf.py`:
   - Quantization: default Q4_K_M (best quality/size ratio for 6GB inference)
   - Also offer Q5_K_M if model is ≤1.5B
3. **Register in Ollama** via Modelfile — **IMPORTANT: the template must match the model family's chat format**:

   ```python
   # In gguf_exporter.py — model family → Ollama template mapping
   OLLAMA_TEMPLATES = {
       "qwen2.5": '"""<|im_start|>system\n{{.System}}<|im_end|>\n<|im_start|>user\n{{.Prompt}}<|im_end|>\n<|im_start|>assistant\n"""',
       "llama3": '"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{{.System}}<|eot_id|><|start_header_id|>user<|end_header_id|>\n{{.Prompt}}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"""',
       "smollm2": '"""<|im_start|>system\n{{.System}}<|im_end|>\n<|im_start|>user\n{{.Prompt}}<|im_end|>\n<|im_start|>assistant\n"""',
       "phi3": '"""<|system|>\n{{.System}}<|end|>\n<|user|>\n{{.Prompt}}<|end|>\n<|assistant|>\n"""',
   }
   ```

   Detect the model family from the base model name and select the correct template. A hardcoded ChatML template will break Llama and Phi models.

   Generated Modelfile:
   ```
   FROM ./model.gguf
   PARAMETER temperature 0.7
   PARAMETER top_p 0.9
   TEMPLATE {selected_template}
   ```
   Then: `ollama create synthboard-{model_name}-{run_id} -f Modelfile`

**Pre-flight disk space check**: Before starting export, estimate required temporary disk space (merged model = ~2x quantized output size). For a 1.5B model: ~3-4GB temp, ~1GB final GGUF. For a 3B model: ~6-8GB temp, ~2GB final. Check available space and block with a clear error if insufficient.

4. **Verify**: run a test prompt through Ollama to confirm the model loads and responds.

### llama.cpp Dependency
The backend must either:
- (A) Bundle a pre-built `llama-quantize` binary for Windows (preferred)
- (B) Use the `llama-cpp-python` package's conversion utilities
- (C) Call `unsloth`'s built-in GGUF export if available in the installed version

Check which method works at startup and cache the result. Do NOT assume any specific method is available — probe and fallback.

---

## Arena Engine (arena_engine.py)

### Battle Flow
1. **Pre-flight check**: Verify at least 2 models are registered in the arena. If not → return 400: "Register at least 2 models to start battles." Also check Ollama is running (`GET http://localhost:11434/api/tags`).
2. User enters a prompt (or picks from a prompt bank)
3. Backend randomly selects two models from the registry
4. Randomly assigns models to Position A and Position B (blind)
5. **Sequential inference with timeout**:
   - Load Model A via Ollama → generate response → record latency (time-to-first-token + total) → unload
   - Load Model B via Ollama → generate response → record latency → unload
   - **httpx timeout = 120 seconds per model**. If Ollama hangs (OOM, model fails to load, service crashed), the request times out instead of hanging forever. On timeout, record the response as "[Generation timed out after 120s]" and still allow voting.
6. Return both responses with blinded labels ("Model A" / "Model B")
7. User votes: **A wins, B wins, Tie, or Skip**
   - Skip records the battle as `winner=NULL` without affecting Elo ratings. Use this when both responses are garbage (truncated, timed out, nonsensical).
8. After vote: reveal model identities, update Elo ratings (skip = no Elo change)

### Elo Rating System
Standard Elo with K=32:
```python
def calculate_elo(rating_a: float, rating_b: float, winner: str, K: int = 32) -> tuple[float, float]:
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a

    if winner == "a":
        score_a, score_b = 1.0, 0.0
    elif winner == "b":
        score_a, score_b = 0.0, 1.0
    else:  # tie
        score_a, score_b = 0.5, 0.5

    new_a = rating_a + K * (score_a - expected_a)
    new_b = rating_b + K * (score_b - expected_b)
    return round(new_a, 1), round(new_b, 1)
```

All models start at Elo 1200. Store full battle history in SQLite.

### Latency Tracking
For every inference, record:
- `time_to_first_token_ms` — measures model load + prompt processing time
- `total_generation_ms` — full response time
- `tokens_generated` — response length
- `tokens_per_second` — throughput

Display these as distributions per model on the leaderboard.

### Prompt Bank
Seed the arena with ~30 diverse evaluation prompts across categories:
- Reasoning (logic puzzles, math)
- Creative writing (story continuation, poetry)
- Code generation (simple Python tasks)
- Instruction following (formatting, constraints)
- Knowledge (factual recall)
- Summarization
- Conversation (multi-turn stubs)

Users can also type custom prompts.

---

## Database Schema (SQLite)

```sql
-- CRITICAL: Enable foreign key enforcement on every connection
-- SQLite disables foreign keys by default. Without this, referential integrity silently breaks.
PRAGMA foreign_keys = ON;

-- Training runs
CREATE TABLE training_runs (
    id TEXT PRIMARY KEY,
    base_model TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    config JSON NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, running, completed, failed, cancelled
    final_loss REAL,
    total_steps INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    checkpoint_path TEXT,
    gguf_path TEXT,
    ollama_model_name TEXT
);

-- Datasets
CREATE TABLE datasets (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    format_detected TEXT,  -- alpaca, sharegpt, qa, raw
    num_samples INTEGER,
    avg_token_length REAL,
    formatted_path TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Models in the arena
CREATE TABLE arena_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,           -- display name
    ollama_name TEXT NOT NULL,    -- ollama model tag
    source TEXT NOT NULL,         -- 'base' or 'fine-tuned'
    training_run_id TEXT,         -- NULL for base models
    elo_rating REAL DEFAULT 1200.0,
    total_battles INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_losses INTEGER DEFAULT 0,
    total_ties INTEGER DEFAULT 0,
    avg_ttft_ms REAL,            -- avg time to first token
    avg_tps REAL,                -- avg tokens per second
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (training_run_id) REFERENCES training_runs(id)
);

-- Battle history
CREATE TABLE battles (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    prompt_category TEXT,
    model_a_id TEXT NOT NULL,
    model_b_id TEXT NOT NULL,
    response_a TEXT,
    response_b TEXT,
    model_a_ttft_ms REAL,
    model_b_ttft_ms REAL,
    model_a_total_ms REAL,
    model_b_total_ms REAL,
    model_a_tokens INTEGER,
    model_b_tokens INTEGER,
    winner TEXT,                  -- 'a', 'b', 'tie', 'skip', NULL (pending vote)
    model_a_elo_before REAL,
    model_b_elo_before REAL,
    model_a_elo_after REAL,
    model_b_elo_after REAL,
    voted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_a_id) REFERENCES arena_models(id),
    FOREIGN KEY (model_b_id) REFERENCES arena_models(id)
);

-- Elo history for charting
CREATE TABLE elo_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    elo_rating REAL NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES arena_models(id)
);

-- Indexes for query performance
CREATE INDEX idx_arena_models_elo ON arena_models(elo_rating DESC);
CREATE INDEX idx_battles_model_a ON battles(model_a_id);
CREATE INDEX idx_battles_model_b ON battles(model_b_id);
CREATE INDEX idx_battles_created ON battles(created_at DESC);
CREATE INDEX idx_elo_history_model ON elo_history(model_id, recorded_at DESC);
CREATE INDEX idx_training_runs_status ON training_runs(status);
```

---

## API Endpoints

### Datasets
- `POST /api/datasets/upload` — upload file, auto-detect format, return preview. **Must validate file content, not just extension**: try-parse the first 1KB to confirm it's valid CSV/JSON/JSONL/Parquet before storing. Reject binary files with `.csv` extension, malformed HTML disguised as `.json`, etc.
- `GET /api/datasets` — list all datasets
- `GET /api/datasets/{id}` — dataset details + sample preview
- `POST /api/datasets/{id}/format` — convert to training format (with optional column mapping)
- `DELETE /api/datasets/{id}` — remove dataset and formatted file

### Training
- `POST /api/training/start` — launch fine-tune (model, dataset_id, config overrides)
- `GET /api/training/runs` — list all training runs
- `GET /api/training/runs/{id}` — run details + final metrics
- `GET /api/training/runs/{id}/stream` — SSE stream of training progress
- `POST /api/training/runs/{id}/cancel` — cancel running training
- `GET /api/training/runs/{id}/logs` — full training log

### Models
- `GET /api/models` — list all arena models (base + fine-tuned)
- `POST /api/models/register-base` — register a base Ollama model for arena
- `POST /api/models/export/{run_id}` — export training run to GGUF + register in Ollama
- `DELETE /api/models/{id}` — remove from arena (optionally delete GGUF)

### Arena
- `POST /api/arena/battle` — generate a new battle (prompt required or random from bank)
- `POST /api/arena/battle/{id}/vote` — submit vote (a/b/tie/skip). Skip records battle but does not update Elo.
- `GET /api/arena/battle/{id}` — get battle details (reveals models after vote)
- `GET /api/arena/history` — paginated battle history

### Leaderboard
- `GET /api/leaderboard` — ranked models by Elo with stats
- `GET /api/leaderboard/{model_id}/history` — Elo history over time
- `GET /api/leaderboard/stats` — aggregate stats (total battles, vote distribution, etc.)

### System
- `GET /api/system/gpu` — current GPU utilization, VRAM, temperature
- `GET /api/system/health` — Ollama status, disk space, training status
- `GET /api/system/disk` — breakdown of space used by checkpoints, GGUFs, datasets

---

## UI Design Direction

**Aesthetic**: Industrial control panel — think NASA mission control meets Bloomberg Terminal. Dark theme mandatory (ML engineers live in dark mode). Dense but readable.

**Key design elements**:
- Monospace font for metrics/logs (JetBrains Mono or Fira Code via Google Fonts)
- Sans-serif for UI chrome (DM Sans or Instrument Sans)
- Color system: dark slate background (#0a0f1a), neon accent for active/success (#00ff88), amber for warnings (#ffaa00), red for errors/OOM (#ff4444), cool blue for neutral data (#4488ff)
- GPU VRAM meter as a persistent bar in the top nav — always visible, color-coded (green/amber/red)
- Training loss curve rendered live with Recharts, dark theme
- Arena: two equal-width panels with a divider, **sequential streaming** (see Arena UX Flow below), latency badges in top-right of each panel
- Leaderboard: sortable table with inline sparkline Elo history charts

### Page Layouts

**Datasets Page**: Left panel = dataset list, right panel = selected dataset preview (table view of first 20 rows). Upload zone at top with drag-and-drop.

**Training Page**: Left panel = training config form (model dropdown, dataset dropdown, hyperparameter sliders with tooltips). Right panel = live training dashboard (loss curve, GPU monitor, step counter, ETA). Bottom = training history table.

**Arena Page**: Full-width. Prompt input at top. Two response panels below (equal width, labeled "Model A" / "Model B"). Four vote buttons centered below: "A is Better" / "Tie" / "B is Better" / "Skip" (dimmed styling, smaller). After voting, model names fade in above each panel with Elo change badges (+12.4 / -12.4). Skip shows models without Elo changes.

**Arena UX Flow (Sequential Streaming)**:
Because inference is sequential (VRAM constraint), the UI must reflect this honestly:
1. User submits prompt → both panels show empty state
2. Panel A header shows "Model A — Generating..." with a pulsing dot. Panel B header shows "Model B — Waiting..." (dimmed).
3. Model A's response streams token-by-token into Panel A. Latency badge populates live (TTFT, then TPS).
4. When Model A completes → Panel A locks. Panel B header switches to "Model B — Generating..." with pulsing dot.
5. Model B's response streams token-by-token into Panel B. Latency badge populates.
6. When Model B completes → both panels locked, vote buttons activate.
This creates a natural "reveal" tension that makes the arena feel engaging, not broken.

**Leaderboard Page**: Full-width table. Columns: Rank, Model Name, Source (base/fine-tuned badge), Elo Rating (with sparkline), Win Rate, Total Battles, Avg Latency (TTFT), Avg TPS. Click a row to expand into a detail panel with Elo history chart, win/loss/tie breakdown pie chart, latency distribution histogram.

---

## Build Order (26 Steps, ~25-30 days realistic)

### Phase 0: Environment Validation (Step 0) — DO THIS BEFORE ANYTHING ELSE
0. **Environment probe (GATE STEP)**. This step determines whether the rest of the project runs on native Windows or WSL2. Do the following in order:
   - Create a fresh Python venv: `python -m venv venv && venv\Scripts\activate`
   - Install PyTorch with CUDA. Pin the exact version that works — do NOT use `pip install torch`. Go to https://pytorch.org/get-started/locally/ and get the command for your CUDA version (likely CUDA 12.1 or 12.4). Example: `pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121`
   - Verify CUDA: `python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"`
   - Install bitsandbytes: `pip install bitsandbytes>=0.42.0`. Verify: `python -c "import bitsandbytes; print(bitsandbytes.__version__)"`
   - Install unsloth per their GitHub README for Windows. Verify: `python -c "from unsloth import FastLanguageModel; print('unsloth OK')"`
   - Test GGUF export path: `python -c "from unsloth import FastLanguageModel; print(hasattr(FastLanguageModel, 'save_pretrained_gguf'))"` — if False, you need llama.cpp Python bindings or a pre-built `llama-quantize` binary.
   - Install `huggingface_hub`: `pip install huggingface_hub && huggingface-cli login` (paste your HF token when prompted). Needed for gated models (Llama 3.2).
   - Record ALL working versions in `requirements.txt` with `pip freeze > requirements.txt`. Copy torch, CUDA, unsloth, bitsandbytes versions into `.env` for reference.
   - **IF ANY OF THE ABOVE FAIL on native Windows**: Install WSL2 (Ubuntu 22.04), install CUDA toolkit inside WSL2, and repeat the above inside WSL2. If WSL2 works, the backend runs in WSL2 and the frontend runs in native Windows cmd. Update the OS constraint accordingly.
   - **Only proceed to Step 1 after `import unsloth`, `import bitsandbytes`, `torch.cuda.is_available()`, and the GGUF probe all pass.**

### Phase 1: Foundation (Steps 1-5)
1. **Scaffold**: Activate the validated venv from Step 0. Create project structure. `npm create vite@latest frontend -- --template react`. Install backend deps: `pip install fastapi uvicorn python-multipart aiosqlite pydantic python-dotenv httpx pyarrow trl`. Create all empty files/folders per architecture. Init git. Commit `requirements.txt` from Step 0.
2. **Database + Config**: Implement `config.py` (all paths, constants, `GATED_MODELS` lookup list, `OLLAMA_TEMPLATES` model-family→template dict). Implement `database.py` with all CREATE TABLE + CREATE INDEX statements. **Critical: execute `PRAGMA foreign_keys = ON` on every new connection.** Write migration runner. Add `.env.example`.
3. **System endpoints**: Implement `/api/system/gpu` with **fallback chain**: try pynvml → fall back to nvidia-smi CLI (full path `C:\Windows\System32\nvidia-smi.exe` on Windows, `/mnt/c/Windows/System32/nvidia-smi.exe` on WSL2) → fall back to returning null GPU stats with a warning. Also implement `/api/system/health`, `/api/system/disk`. Test with curl.
4. **Frontend shell**: Install Tailwind, react-router-dom, recharts, axios, react-dropzone. Build layout (Sidebar + TopBar with GPU meter). Create all page components as stubs. Verify routing works.
5. **GPU Monitor component**: Build `GpuMonitor.jsx` that polls `/api/system/gpu` every 5 seconds. Render VRAM bar in TopBar. Style with the industrial dark theme.

### Phase 2: Dataset Pipeline (Steps 6-9)
6. **Upload endpoint**: Implement `POST /api/datasets/upload` — accept file, save to `data/uploads/`, detect format, store metadata in DB. Return dataset ID + detected format + preview.
7. **Dataset formatter service**: Implement `dataset_formatter.py` — auto-detect (Alpaca/ShareGPT/QA/raw), convert to standardized JSONL in `data/formatted/`. Handle edge cases (empty rows, missing fields, encoding issues).
8. **Dataset API completion**: Implement remaining endpoints (list, detail, format, delete). Add column-mapping support for unknown formats.
9. **Dataset UI**: Build `DatasetsPage.jsx` with `UploadZone`, `DataPreview` (table view), `FormatSelector` (for manual column mapping). Wire to all API endpoints.

### Phase 3: Fine-Tuning Engine (Steps 10-15)
10. **Capabilities endpoint + GGUF probe**: Write a startup probe that checks unsloth + bitsandbytes + CUDA + GGUF export path availability (test `save_pretrained_gguf`, fallback to llama.cpp bindings, fallback to external binary). Log versions. Create `/api/system/capabilities` endpoint that reports: available model tiers, GGUF export method (unsloth-native / llama-cpp-python / external-binary / unavailable), CUDA version, VRAM total.
11. **Training engine core**: Implement `training_engine.py` — load model via unsloth, apply QLoRA config, prepare dataset with tokenizer, configure SFTTrainer. **Before first model download, check `config.GATED_MODELS` — if the selected model is in this list and `HF_TOKEN` is not set, abort with a clear error message (not a cryptic 401).** Compute `total_steps` pre-flight and store in DB. Run a test with 5 steps on a tiny dummy dataset to validate the pipeline end-to-end.
12. **Training SSE streaming**: Implement custom `TrainerCallback` that pushes events to a **bounded `queue.Queue(maxsize=100)`**. Use a **broadcast pattern** (list of subscriber queues) so multiple browser tabs can subscribe. SSE endpoint must check `await request.is_disconnected()` on every iteration and deregister the subscriber's queue on disconnect. Implement cancel via threading event. Stream: step, loss, learning rate, VRAM usage, ETA.
13. **Training API**: Wire up `POST /api/training/start`, `GET /stream`, `POST /cancel`, `GET /runs`. **Critical**: `trainer.train()` is blocking — run it via `loop.run_in_executor(ThreadPoolExecutor(max_workers=1))`. Enforce **global training lock**: if any run has `status='running'`, return 409. Implement VRAM guard (pre-flight check before allowing training start).
14. **Training UI — Config**: Build `TrainingConfig.jsx` — model dropdown (with tier labels + VRAM estimates), dataset dropdown, hyperparameter controls (sliders for rank, alpha, epochs, lr, max_seq_length). All have sensible defaults + tooltips.
15. **Training UI — Dashboard**: Build `TrainingProgress.jsx` — live loss curve (Recharts), step counter, ETA, VRAM gauge, cancel button. Show training history table below.

### Phase 4: Model Export (Steps 16-17)
16. **GGUF export pipeline**: Implement `gguf_exporter.py` — use the export method identified in Step 10 (unsloth-native preferred). **Pre-flight disk space check** (merged model needs ~2x final GGUF size temporarily). Merge LoRA adapters, convert to GGUF (Q4_K_M), generate Modelfile **using `config.OLLAMA_TEMPLATES` for the correct model family's chat template** (do NOT hardcode ChatML), register in Ollama via subprocess. Verify with a test inference call.
17. **Models page**: Build `ModelsPage.jsx` — list all models (base + fine-tuned), show source badge, Ollama status indicator. "Export to Arena" button for completed training runs. "Register Base Model" button (pick from installed Ollama models).

### Phase 5: Arena (Steps 18-22)
18. **Arena engine**: Implement `arena_engine.py` — sequential inference via Ollama API (httpx, **timeout=120s per model**), model load/unload lifecycle, latency measurement (TTFT, total, TPS). **Pre-flight: check at least 2 models registered, return 400 if not. Check Ollama is running.** Handle timeout and OOM gracefully — on timeout, record response as "[Generation timed out]" and still allow voting.
19. **Elo calculator + battle API**: Implement `elo_calculator.py`. Wire up `POST /api/arena/battle`, `POST /vote` (**accept a/b/tie/skip — skip records battle with `winner=NULL`, no Elo change**), `GET /history`. Create `data/prompt_bank.json` with 30 diverse prompts (categorized: reasoning, creative, code, instruction, knowledge, summarization, conversation). Load from file, not hardcoded.
20. **Arena UI — Battle view**: Build `ArenaPage.jsx` with **sequential streaming UX**: prompt input → Panel A streams live while Panel B shows "Waiting..." → Panel A locks → Panel B streams live → both lock → vote buttons activate. Include `ResponsePanel` with latency badges, `VoteButtons` (**4 buttons: A Better / Tie / B Better / Skip**), and model reveal animation after voting.
21. **Leaderboard API**: Implement `GET /api/leaderboard` with all stats, `GET /history` for Elo chart data.
22. **Leaderboard UI**: Build `LeaderboardPage.jsx` — sortable table with sparklines (Recharts), expandable rows with Elo history chart, win/loss breakdown, latency distribution.

### Phase 6: Polish + Ship (Steps 23-25)
23. **Error handling + edge cases + cleanup**: Empty states for all pages. Loading skeletons. Error toasts. Handle Ollama not running. Handle training OOM gracefully (catch CUDA OOM, report in UI, suggest fixes). Disk space warnings. **Implement disk cleanup utility**: UI button to delete old checkpoints, orphaned GGUFs, and expired training runs. Show space reclaimed. **Cancelled training cleanup**: when a run is cancelled, mark as `cancelled` in DB and delete partial checkpoints from `data/checkpoints/{run_id}/` immediately — don't leave orphans.
24. **README + demo data**: Write comprehensive README with screenshots, setup instructions, hardware requirements. **Critical README callout**: `pip install -r requirements.txt` will NOT install torch correctly — users must run the CUDA-specific torch install command from Step 0 FIRST, then install remaining deps. Create demo dataset: **100 general instruction-following samples** (mix of QA, summarization, simple coding, formatting tasks) in Alpaca JSONL format, no copyrighted content, stored at `data/demo/alpaca_demo_100.jsonl`.
25. **Final integration test**: Full E2E: upload dataset → format → fine-tune (3 epochs on demo data) → export GGUF → register in arena → run 5 battles → check leaderboard. Fix any issues found. Final git push.

---

## Claude Code Workflow Rules

1. **One step per prompt**. Do NOT explore the full codebase. Do NOT refactor things that aren't part of the current step.
2. **One git commit per verified step**. Commit message format: `Step {N}: {description}`.
3. **Test before committing**. Every step must have a verification — either a curl command, a UI check, or a log output.
4. **Do NOT install packages preemptively**. Install only what the current step needs.
5. **Do NOT modify files outside the current step's scope** unless a bug in a previous step blocks progress.
6. **If something fails, fix it in the current step** — do not move on with broken state.
7. **Windows cmd syntax only** (unless Step 0 fell back to WSL2, in which case bash for backend, cmd for frontend). Use `&&` for chaining in cmd. No PowerShell-specific commands.
8. **NEVER start uvicorn with `--reload` during training sessions.** Hot-reload restarts the process, killing any active training thread. Use `uvicorn main:app --host 0.0.0.0 --port 8000` without `--reload` for any step involving training (Steps 10+). Add a comment `# DO NOT use --reload during training` in the startup command.

---

## Known Landmines (Read Before Building)

1. **unsloth on Windows**: Installation can be painful. May need specific torch + CUDA + triton versions. **Step 0 is the gate for this** — if native Windows fails, WSL2 is the fallback. Pin ALL working versions in requirements.txt once Step 0 passes. Never upgrade torch/unsloth/bitsandbytes mid-project.

2. **bitsandbytes on Windows**: Needs the `bitsandbytes-windows` fork or bitsandbytes>=0.42.0 which has native Windows support. Test with `python -c "import bitsandbytes; print(bitsandbytes.__version__)"` before proceeding.

3. **Ollama model unloading**: Setting `keep_alive=0` in the API call tells Ollama to unload after responding. Verify this actually frees VRAM (check nvidia-smi). If not, use `ollama stop {model}` as a fallback.

4. **SFTTrainer callback for SSE**: The `TrainerCallback` class allows `on_log` and `on_step_end` hooks. Use `on_log` for loss values (they're only emitted every `logging_steps`). Use `on_step_end` for VRAM polling. Push to a thread-safe queue that the SSE endpoint reads from.

5. **GGUF conversion**: unsloth has a built-in `model.save_pretrained_gguf()` method. This is probed in Step 0 and verified in Step 10. If unavailable, fallback chain: (A) `llama-cpp-python` package conversion, (B) pre-built `llama-quantize` Windows binary from llama.cpp releases. The method may not support all quantization types — Q4_K_M should work across all paths.

6. **8GB RAM constraint during training**: The SFTTrainer loads the dataset into memory. For datasets >10k samples, implement streaming via `IterableDataset`. Set `dataloader_num_workers=0` and `dataloader_pin_memory=False`.

7. **Windows multiprocessing**: `dataloader_num_workers > 0` will crash on Windows without `if __name__ == "__main__"` guard. Always use 0.

8. **Ollama API for streaming**: Use `POST http://localhost:11434/api/generate` with `"stream": true` for token-by-token responses. Parse NDJSON lines. Measure TTFT as time from request to first non-empty response chunk.

9. **fp16 vs bf16 on RTX 3050**: The 3050 (GA106, Ampere-lite) supports bf16 but performance is identical to fp16 on this chip. Use fp16 for broadest compatibility.

10. **Gradient checkpointing + unsloth**: Use `use_gradient_checkpointing="unsloth"` (string, not boolean). This uses unsloth's optimized implementation that's faster than the HuggingFace default.

11. **HuggingFace gated models**: Llama-3.2-1B, Llama-3.2-3B, and Llama-3.1-8B are all gated. They require: (A) accepting the license on the model page on huggingface.co, (B) a valid HF_TOKEN set in the environment. Without both, the download silently fails or returns a 401. Qwen2.5 and SmolLM2 are fully open and need no auth. The training engine must check gated status before attempting download and show a clear error if HF_TOKEN is missing.

12. **torch version pinning**: Never run `pip install torch` without a version pin. unsloth requires specific torch + CUDA combos. Pin the exact versions from Step 0 in requirements.txt. If someone runs `pip install -r requirements.txt` and gets a different torch, everything breaks. Add a comment in requirements.txt: `# DO NOT UPGRADE — these versions validated in Step 0`.

13. **`trainer.train()` blocks the async event loop**: This is the #1 runtime bug. SFTTrainer.train() is synchronous. FastAPI is async. If called directly in an async route handler, the entire server freezes — no SSE events, no other endpoints respond. MUST use `loop.run_in_executor(ThreadPoolExecutor(max_workers=1))`. This is enforced in the Fine-Tuning Engine section but if you miss it, nothing works.

14. **`uvicorn --reload` kills training**: Hot-reload restarts the process, killing any active training thread with no cleanup. The training run stays `status='running'` in the DB forever (zombie run). During development of Steps 10+, always start uvicorn without `--reload`. If a zombie run exists, manually update it to `failed` in the DB before starting a new one.

15. **Ollama Modelfile template must match model family**: A ChatML template (`<|im_start|>`) works for Qwen2.5 and SmolLM2 but breaks Llama 3.x and Phi models. The GGUF exporter must look up the correct template from `config.OLLAMA_TEMPLATES` based on the base model family. If this is wrong, the arena model will generate garbage or refuse to respond.

16. **`nvidia-smi` path varies on Windows**: On some machines it's in PATH, on others it's only at `C:\Windows\System32\nvidia-smi.exe`. The GPU monitor must try both. On WSL2, the path is `/mnt/c/Windows/System32/nvidia-smi.exe` OR the CUDA toolkit's WSL2 version may provide it natively. Implement a probe that caches the working path at startup.

17. **requirements.txt chicken-and-egg with torch**: `pip install -r requirements.txt` will install CPU-only torch (the default PyPI package) unless the user first runs the CUDA-specific install command. The README must explicitly document this two-step install. Consider splitting into `requirements-core.txt` (torch, unsloth, bitsandbytes — manual install) and `requirements.txt` (everything else — safe to pip install).

---

## Environment Setup (.env.example)

```env
# SynthBoard Configuration
OLLAMA_BASE_URL=http://localhost:11434
DATA_DIR=./data
DATABASE_PATH=./synthboard.db
MAX_UPLOAD_SIZE_MB=500
DEFAULT_MAX_SEQ_LENGTH=1024
VRAM_SAFETY_MARGIN_MB=500
TRAINING_LOG_DIR=./logs

# HuggingFace — REQUIRED for gated models (Llama 3.2, etc.)
# Get your token: https://huggingface.co/settings/tokens
# Also run: huggingface-cli login
HF_TOKEN=

# Torch version — DO NOT change these after Step 0 validates them.
# These get filled in by Step 0 after a successful environment probe.
TORCH_VERSION=
CUDA_VERSION=
UNSLOTH_VERSION=
```

---

## Stress Test Checklist (Run Before Calling It Done)

### Data Pipeline
- [ ] Upload a 50MB CSV dataset — should not crash or freeze
- [ ] Upload a malformed JSON file — should return a clear error, not 500
- [ ] Upload a binary file renamed to `.csv` — should reject with MIME validation error, not crash in formatter
- [ ] Upload a `.parquet` file — should read successfully (pyarrow installed)

### Fine-Tuning
- [ ] Start a fine-tune on Qwen2.5-1.5B with 1000 samples, 3 epochs — should complete without OOM
- [ ] Cancel a running fine-tune — should stop within 10 seconds, free VRAM, **delete partial checkpoints**
- [ ] Try to start a second fine-tune while one is running — should return 409, not OOM
- [ ] Start a fine-tune and verify the SSE stream emits events in real-time (not all at once after training completes)
- [ ] Start a fine-tune, close the browser tab, reopen — SSE should reconnect and resume showing progress
- [ ] Open two browser tabs on the Training page during a run — both should show progress (broadcast pattern)
- [ ] Check VRAM stays below 6GB during fine-tuning (nvidia-smi every 30s)
- [ ] Check RAM stays below 7.5GB during dataset processing (taskmgr)
- [ ] Try to fine-tune a Llama 3.2 model without HF_TOKEN set — should show a clear auth error before downloading

### Model Export
- [ ] Export a fine-tuned model to GGUF — should appear in `ollama list` after
- [ ] Export a fine-tuned Llama model — Modelfile template should use Llama format, NOT ChatML
- [ ] Try to export when disk space is low — should show a clear space error, not crash mid-export

### Arena
- [ ] Run 10 arena battles — Elo ratings should change, leaderboard should update
- [ ] Run an arena battle while Ollama is not running — should show a clear error, not hang
- [ ] Run an arena battle with only 1 model registered — should return 400 with helpful message
- [ ] Trigger a timeout (stop Ollama mid-generation) — should timeout after 120s, not hang forever
- [ ] Use the Skip button — battle should record but Elo should not change
- [ ] Verify sequential streaming UX: Panel A streams → Panel B shows "Waiting..." → Panel B streams

### General
- [ ] Open the app after a fresh reboot with no training history — all pages should render (empty states)
- [ ] Run a full cycle: upload → format → train → export → arena — end-to-end in one session
- [ ] Start uvicorn with `--reload`, begin a training run, and trigger a reload — **document this as a known issue**, not a fix