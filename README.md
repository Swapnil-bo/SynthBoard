# SynthBoard

**Local fine-tuning pipeline + blind model arena for consumer GPUs.**

![Python 3.13+](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)
![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

Upload a dataset, auto-format it for fine-tuning, QLoRA fine-tune a model on consumer hardware, export to GGUF, and pit it against base models in a blind side-by-side arena with Elo ratings. The entire lifecycle — data prep, training, deployment, evaluation — runs on a single RTX 3050 6GB.

<!-- Screenshots coming soon -->

---

## Features

- **Dataset Pipeline** — Upload CSV, JSONL, JSON, or Parquet files. Auto-detects Alpaca, ShareGPT, Q&A, and raw text formats. Manual column mapping for unknown schemas. Preview and stats before training.
- **QLoRA Fine-Tuning** — 4-bit quantized training via unsloth + trl SFTTrainer. Live loss curves, GPU monitoring, and ETA via Server-Sent Events. One-click cancel with VRAM cleanup.
- **GGUF Export** — Merge LoRA adapters, quantize to Q4_K_M, auto-register in Ollama with the correct chat template per model family (Qwen, Llama, Phi, SmolLM).
- **Blind Arena** — Side-by-side model comparison with sequential streaming inference. Vote A/B/Tie/Skip with blinded model identities revealed after voting.
- **Elo Leaderboard** — Standard Elo ratings (K=32), sparkline history charts, win rate breakdowns, latency distributions (TTFT, tokens/sec).
- **GPU-Aware** — Persistent VRAM meter, pre-flight VRAM checks before training, automatic sequential inference to stay within 6GB.
- **Disk Management** — Built-in cleanup utility for old checkpoints, orphaned GGUFs, and expired training runs.

---

## Hardware Requirements

| Component | Minimum | Notes |
|-----------|---------|-------|
| **GPU** | NVIDIA RTX 3050 6GB | Any 6GB+ CUDA GPU works. 8GB+ is more comfortable. |
| **RAM** | 8GB DDR4 | Dataset processing streams/chunks to stay within limits. |
| **Disk** | 50GB free | Fine-tuned checkpoints + GGUF exports consume significant space. |
| **OS** | Windows 11 | Tested on Windows 11 Pro. WSL2 is a fallback if native CUDA fails. |

---

## Setup

### Prerequisites

- **Python 3.13+** — [python.org](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **NVIDIA GPU drivers** — Latest from [nvidia.com](https://www.nvidia.com/Download/index.aspx)
- **Ollama** — [ollama.com](https://ollama.com/) (required for arena inference and model serving)

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/your-username/synthboard.git
cd synthboard
python -m venv venv
venv\Scripts\activate
```

### 2. Install PyTorch with CUDA (DO THIS FIRST)

> **WARNING:** `pip install -r requirements.txt` alone will install CPU-only PyTorch from PyPI and **everything will break**. You must install the CUDA build of PyTorch first.

Go to [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/) and select your CUDA version. Example for CUDA 13.0:

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
```

Verify CUDA is available:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# Expected: True NVIDIA GeForce RTX 3050
```

### 3. Install remaining Python dependencies

```bash
pip install -r requirements.txt
```

This installs unsloth, bitsandbytes, FastAPI, and all other backend dependencies. PyTorch is excluded from this file because it requires the CUDA-specific install from Step 2.

### 4. Configure environment

```bash
copy .env.example .env
```

Edit `.env` and fill in your torch/CUDA versions. If you plan to fine-tune gated models (Llama 3.2), add your HuggingFace token:

```env
HF_TOKEN=hf_your_token_here
```

You also need to accept the model license on huggingface.co and run:

```bash
huggingface-cli login
```

### 5. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 6. Set up Ollama

Install Ollama from [ollama.com](https://ollama.com/), then pull at least 2 models for the arena:

```bash
ollama pull qwen2.5:1.5b
ollama pull smollm2:1.7b
```

Other recommended models:

```bash
ollama pull qwen2.5:3b        # Larger, tighter on VRAM
ollama pull llama3.2:1b        # Fast but limited
ollama pull mistral:7b-instruct-v0.3-q4_K_M  # Arena inference only (too large to fine-tune)
```

---

## Running the App

### Start the backend

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

> **Do NOT use `--reload` if you plan to fine-tune.** Hot-reload restarts the process and kills any active training thread with no cleanup, leaving a zombie run in the database.

### Start the frontend (separate terminal)

```bash
cd frontend
npm run dev
```

### Access the app

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

---

## Usage Walkthrough

### 1. Upload a Dataset

Navigate to the **Datasets** page. Drag and drop a CSV, JSONL, JSON, or Parquet file (or use the included demo dataset at `data/demo/alpaca_demo_100.jsonl`). SynthBoard auto-detects the format and shows a preview.

### 2. Format for Training

Click **Format** on your dataset. For auto-detected formats (Alpaca, ShareGPT, Q&A), conversion is automatic. For unknown formats, map your columns to `instruction`, `input`, and `output` fields.

### 3. Fine-Tune a Model

Go to the **Training** page. Select a base model (Qwen2.5-1.5B recommended for first run), pick your formatted dataset, and adjust hyperparameters if needed. Click **Start Training**.

Watch the live loss curve, GPU utilization, and ETA update in real-time via SSE streaming. Training runs in a background thread — the UI stays responsive.

### 4. Export to GGUF

Once training completes, go to the **Models** page and click **Export to Arena** on your training run. This merges LoRA adapters, quantizes to GGUF (Q4_K_M), and registers the model in Ollama automatically.

### 5. Battle in the Arena

Navigate to the **Arena** page. Type a prompt or pick one from the prompt bank. Two randomly selected models generate responses sequentially (Model A streams first, then Model B). Vote on which response is better — model identities are revealed after voting.

### 6. Check the Leaderboard

The **Leaderboard** page shows all models ranked by Elo rating with sparkline history, win rates, battle counts, and latency metrics.

---

## Tech Stack

### Backend
| Package | Purpose |
|---------|---------|
| FastAPI | Async REST API + SSE streaming |
| unsloth | QLoRA fine-tuning (2-4x faster, 60-70% less VRAM) |
| trl (SFTTrainer) | Supervised fine-tuning trainer |
| transformers + peft + bitsandbytes | Model loading, QLoRA config, 4-bit quantization |
| Ollama | Local model serving for arena inference |
| httpx | Async HTTP client for Ollama API |
| aiosqlite | Async SQLite for persistence |
| pandas + pyarrow | Dataset processing (chunked reads) |

### Frontend
| Package | Purpose |
|---------|---------|
| React 19 + Vite | Single-page application |
| Tailwind CSS 4 | Styling (industrial dark theme) |
| Recharts | Loss curves, Elo history, latency charts |
| react-router-dom v7 | Page navigation |
| react-dropzone | File upload UX |
| axios | API calls |

### Infrastructure
| Component | Purpose |
|-----------|---------|
| Ollama | Local model serving (user-installed) |
| SQLite | Zero-config persistence |
| SSE (EventSource) | Real-time training progress |
| llama.cpp | GGUF quantization (pre-built binaries) |

---

## Project Structure

```
synthboard/
├── backend/
│   ├── main.py                     # FastAPI app entry, CORS, lifespan
│   ├── config.py                   # Paths, constants, hardware limits
│   ├── routers/
│   │   ├── datasets.py             # Upload, validate, preview, format
│   │   ├── training.py             # Fine-tune launch, SSE, cancel
│   │   ├── models.py               # List, export GGUF, register in Ollama
│   │   ├── arena.py                # Battle generation, voting
│   │   ├── leaderboard.py          # Elo rankings, stats, history
│   │   └── system.py               # GPU stats, disk usage, health
│   ├── services/
│   │   ├── dataset_formatter.py    # Auto-detect + convert formats
│   │   ├── training_engine.py      # unsloth QLoRA orchestration
│   │   ├── training_broadcaster.py # SSE broadcast to multiple tabs
│   │   ├── gguf_exporter.py        # Checkpoint → GGUF → Ollama
│   │   ├── model_manager.py        # Ollama lifecycle management
│   │   ├── arena_engine.py         # Sequential inference, battle logic
│   │   └── elo_calculator.py       # Elo rating math + persistence
│   ├── models/                     # Pydantic schemas
│   ├── db/database.py              # SQLite setup + migrations
│   └── utils/                      # GPU monitor, validators
├── frontend/
│   ├── src/
│   │   ├── pages/                  # Datasets, Training, Models, Arena, Leaderboard
│   │   ├── components/             # Layout, dataset, training, arena, leaderboard
│   │   ├── hooks/                  # useSSE, useArena, useGpuStats
│   │   └── lib/                    # API client, constants
│   └── index.html
├── data/
│   ├── demo/alpaca_demo_100.jsonl  # 100-sample demo dataset
│   ├── prompt_bank.json            # 30 arena evaluation prompts
│   ├── uploads/                    # Raw uploaded datasets
│   ├── formatted/                  # Training-ready datasets
│   ├── checkpoints/                # QLoRA adapter checkpoints
│   └── exports/                    # GGUF files
├── requirements.txt
├── .env.example
└── CLAUDE.md                       # Full build spec
```

---

## Supported Models

### Tier 1 — Comfortable (recommended)

| Model | Params | Training VRAM | Inference VRAM | Notes |
|-------|--------|---------------|----------------|-------|
| Qwen2.5-1.5B | 1.5B | ~3.0-3.5 GB | ~1.2 GB | Best default choice |
| SmolLM2-1.7B | 1.7B | ~3.0-3.5 GB | ~1.2 GB | Good alternative |
| Llama-3.2-1B | 1B | ~2.5-3.0 GB | ~1.0 GB | Fast but limited. Gated — needs HF token. |

### Tier 2 — Tight (monitor VRAM)

| Model | Params | Training VRAM | Inference VRAM | Notes |
|-------|--------|---------------|----------------|-------|
| Qwen2.5-3B | 3B | ~4.5-5.5 GB | ~2.0 GB | Batch size 1 only |
| Llama-3.2-3B | 3B | ~4.5-5.5 GB | ~2.0 GB | Gated — needs HF token |
| Phi-3-mini-4k | 3.8B | ~5.0-5.5 GB | ~2.5 GB | Borderline, test first |

### Tier 3 — Arena Inference Only (too large to fine-tune on 6GB)

| Model | Params | Inference VRAM | Notes |
|-------|--------|----------------|-------|
| Mistral-7B-Instruct-v0.3 | 7B | ~4.5 GB | Q4_K_M GGUF only |
| Llama-3.1-8B-Instruct | 8B | ~4.5 GB | Q4_K_M GGUF only |
| Qwen2.5-7B-Instruct | 7B | ~4.5 GB | Q4_K_M GGUF only |

---

## Known Limitations

- **7B+ models cannot be fine-tuned** on 6GB VRAM — they will OOM. Use them in the arena via pre-quantized GGUF only.
- **Arena inference is sequential, not parallel.** For 3B+ models, two simultaneous loads would exceed VRAM. Model A generates first, then Model B. The UI reflects this with a "Waiting..." state.
- **Windows-specific.** The training stack (unsloth, bitsandbytes, triton-windows) is validated on Windows 11. Linux/macOS may work but is untested.
- **One training run at a time.** The backend enforces a global lock — concurrent fine-tuning jobs would OOM instantly.
- **Flash Attention 2 not available** on RTX 3050. Xformers is used as the attention backend instead.
- **GGUF export downloads the full FP16 base model** (~3GB for 1.5B params) for LoRA merging, even though training used 4-bit. This is expected and requires temporary disk space (~2x the final GGUF size).
- **Gated models (Llama 3.2)** require accepting the license on huggingface.co and setting `HF_TOKEN` in `.env`. Without this, downloads fail with a cryptic 401.
- **`uvicorn --reload` kills training.** Never use hot-reload during fine-tuning sessions. The process restart kills the training thread with no cleanup.

---

## API Reference

The backend exposes a full REST API. Interactive docs are available at `http://localhost:8000/docs` when the server is running.

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/datasets/upload` | Upload and auto-detect dataset format |
| GET | `/api/datasets` | List all datasets |
| POST | `/api/datasets/{id}/format` | Convert dataset to training format |
| POST | `/api/training/start` | Launch a fine-tuning run |
| GET | `/api/training/runs/{id}/stream` | SSE stream of training progress |
| POST | `/api/training/runs/{id}/cancel` | Cancel active training |
| POST | `/api/models/export/{run_id}` | Export training run to GGUF + Ollama |
| POST | `/api/arena/battle` | Generate a new blind battle |
| POST | `/api/arena/battle/{id}/vote` | Submit vote (a/b/tie/skip) |
| GET | `/api/leaderboard` | Ranked models by Elo |
| GET | `/api/system/gpu` | Current GPU utilization and VRAM |
| GET | `/api/system/health` | Ollama status, disk space, training status |

---

