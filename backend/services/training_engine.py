"""
unsloth QLoRA fine-tuning orchestration.

This module provides a SYNCHRONOUS run_training() function. It will be called
via ThreadPoolExecutor in the training router (Step 13) so that the FastAPI
event loop is not blocked.

Key responsibilities:
- Load model via unsloth FastLanguageModel (4-bit quantized)
- Apply QLoRA adapters via get_peft_model
- Prepare dataset: load formatted JSONL, apply Alpaca/chat template, tokenize
- Configure and run SFTTrainer
- Compute total_steps pre-flight
- Check gated model auth before downloading
- TrainerCallback for SSE progress broadcasting
- Cancel support via threading.Event
- Return result dict with final_loss, checkpoint_path, total_time
"""
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import torch
from datasets import Dataset
from transformers import TrainerCallback, TrainerControl, TrainerState
from transformers import TrainingArguments as HfTrainingArguments

from backend.config import (
    CHECKPOINTS_DIR,
    GATED_MODELS,
    HF_TOKEN,
    MODEL_TIERS,
    QLORA_DEFAULTS,
    TRAINING_DEFAULTS,
)
from backend.services.training_broadcaster import TrainingEvent, get_broadcaster
from backend.utils.gpu_monitor import get_gpu_stats

logger = logging.getLogger(__name__)

# Alpaca prompt template — used to format instruction/input/output into a
# single string for causal LM training.
ALPACA_TEMPLATE = """Below is an instruction that describes a task, paired with further context. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Input:
{input}

### Response:
{output}"""

ALPACA_TEMPLATE_NO_INPUT = """Below is an instruction that describes a task. Write a response that appropriately completes the request.

### Instruction:
{instruction}

### Response:
{output}"""


class TrainingCancelledError(Exception):
    """Raised when a training run is cancelled via cancel_event."""
    pass


# ---------------------------------------------------------------------------
# TrainerCallback for SSE progress
# ---------------------------------------------------------------------------

class SynthBoardTrainerCallback(TrainerCallback):
    """
    HuggingFace TrainerCallback that pushes training progress events to the
    SSE broadcast system.

    - on_log: emits loss, learning_rate, step (only fires every logging_steps)
    - on_step_end: emits VRAM usage, computes ETA (fires every step)
    - on_save: emits checkpoint event
    - on_train_end: emits complete event
    - Checks cancel_event on each step to support cancellation
    """

    def __init__(
        self,
        run_id: str,
        total_steps: int,
        cancel_event: Optional[threading.Event] = None,
        start_time: Optional[float] = None,
    ):
        super().__init__()
        self.run_id = run_id
        self.total_steps = total_steps
        self.cancel_event = cancel_event
        self.start_time = start_time or time.time()
        self.broadcaster = get_broadcaster(run_id)
        self._last_loss: Optional[float] = None
        self._last_lr: Optional[float] = None

    def on_log(
        self,
        args: HfTrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        logs: Optional[dict] = None,
        **kwargs,
    ):
        """Fires every logging_steps. Contains loss and learning_rate."""
        if logs is None:
            return
        loss = logs.get("loss")
        lr = logs.get("learning_rate")
        if loss is not None:
            self._last_loss = loss
        if lr is not None:
            self._last_lr = lr

        # Get VRAM usage
        vram_used_mb = None
        gpu_stats = get_gpu_stats()
        if gpu_stats:
            vram_used_mb = gpu_stats.vram_used_mb

        # Compute ETA
        current_step = int(state.global_step)
        eta_seconds = self._compute_eta(current_step)

        self.broadcaster.push(TrainingEvent(
            event_type="progress",
            data={
                "step": current_step,
                "total_steps": self.total_steps,
                "loss": round(loss, 4) if loss is not None else None,
                "learning_rate": lr,
                "vram_used_mb": vram_used_mb,
                "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
            },
        ))

    def on_step_end(
        self,
        args: HfTrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs,
    ):
        """Fires every step. Check cancel, emit VRAM on non-log steps."""
        # Check cancellation
        if self.cancel_event is not None and self.cancel_event.is_set():
            logger.info("Training cancelled by user at step %d", state.global_step)
            control.should_training_stop = True
            return

    def on_save(
        self,
        args: HfTrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs,
    ):
        """Fires when a checkpoint is saved."""
        current_step = int(state.global_step)
        checkpoint_path = str(Path(args.output_dir) / f"checkpoint-{current_step}")
        self.broadcaster.push(TrainingEvent(
            event_type="checkpoint",
            data={
                "step": current_step,
                "path": checkpoint_path,
            },
        ))

    def on_train_end(
        self,
        args: HfTrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs,
    ):
        """Fires when training completes (success or early stop)."""
        # If cancelled, emit cancelled event instead of complete
        if self.cancel_event is not None and self.cancel_event.is_set():
            elapsed = time.time() - self.start_time
            self.broadcaster.push(TrainingEvent(
                event_type="cancelled",
                data={
                    "step": int(state.global_step),
                    "total_steps": self.total_steps,
                    "total_time_seconds": round(elapsed, 1),
                    "message": "Training cancelled by user.",
                },
            ))
            return

        elapsed = time.time() - self.start_time
        self.broadcaster.push(TrainingEvent(
            event_type="complete",
            data={
                "step": int(state.global_step),
                "total_steps": self.total_steps,
                "final_loss": round(self._last_loss, 4) if self._last_loss is not None else None,
                "total_time_seconds": round(elapsed, 1),
            },
        ))

    def _compute_eta(self, current_step: int) -> Optional[float]:
        """Estimate remaining time based on elapsed time and progress."""
        if current_step <= 0 or self.total_steps <= 0:
            return None
        elapsed = time.time() - self.start_time
        rate = elapsed / current_step  # seconds per step
        remaining_steps = self.total_steps - current_step
        return rate * remaining_steps


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class TrainingResult:
    """Returned by run_training after completion."""
    success: bool
    run_id: str
    final_loss: Optional[float] = None
    total_steps: int = 0
    total_time_seconds: float = 0.0
    checkpoint_path: Optional[str] = None
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_gated_model(model_name: str) -> None:
    """Raise if model is gated and HF_TOKEN is not configured."""
    if model_name in GATED_MODELS and not HF_TOKEN:
        raise PermissionError(
            f"Model '{model_name}' is gated and requires a HuggingFace token. "
            f"Set HF_TOKEN in your .env file and accept the model license at "
            f"https://huggingface.co. Then restart the server."
        )


def _load_formatted_dataset(dataset_path: str) -> list[dict]:
    """Load a formatted JSONL file into a list of dicts."""
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Formatted dataset not found: {dataset_path}")

    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    if not samples:
        raise ValueError(f"Dataset is empty: {dataset_path}")

    return samples


def _format_alpaca_sample(sample: dict, eos_token: str) -> str:
    """Format a single Alpaca-format sample into a training string."""
    instruction = sample.get("instruction", "")
    inp = sample.get("input", "")
    output = sample.get("output", "")

    if inp.strip():
        text = ALPACA_TEMPLATE.format(
            instruction=instruction, input=inp, output=output,
        )
    else:
        text = ALPACA_TEMPLATE_NO_INPUT.format(
            instruction=instruction, output=output,
        )
    return text + eos_token


def _format_chat_sample(sample: dict, tokenizer) -> str:
    """Format a ShareGPT/chat-format sample using the tokenizer's chat template."""
    conversations = sample.get("conversations", [])
    text = tokenizer.apply_chat_template(
        conversations, tokenize=False, add_generation_prompt=False,
    )
    return text


def _build_dataset(
    raw_samples: list[dict],
    tokenizer,
) -> Dataset:
    """
    Convert raw JSONL samples into a HuggingFace Dataset with a 'text' column
    ready for SFTTrainer.
    """
    eos_token = tokenizer.eos_token or ""

    first = raw_samples[0]
    is_chat = "conversations" in first

    texts = []
    for sample in raw_samples:
        if is_chat:
            text = _format_chat_sample(sample, tokenizer)
        else:
            text = _format_alpaca_sample(sample, eos_token)
        texts.append(text)

    return Dataset.from_dict({"text": texts})


def compute_total_steps(
    num_samples: int,
    batch_size: int,
    gradient_accumulation_steps: int,
    num_epochs: int,
    max_steps: int = 0,
) -> int:
    """
    Pre-compute total training steps.
    If max_steps > 0, that takes precedence over epoch-based calculation.
    """
    if max_steps > 0:
        return max_steps
    steps_per_epoch = math.ceil(num_samples / batch_size / gradient_accumulation_steps)
    return steps_per_epoch * num_epochs


# ---------------------------------------------------------------------------
# Main training function
# ---------------------------------------------------------------------------

def run_training(
    run_id: str = "test",
    model_name: str = "unsloth/Qwen2.5-1.5B-bnb-4bit",
    dataset_path: str = "",
    # QLoRA config overrides
    r: int = QLORA_DEFAULTS["r"],
    lora_alpha: int = QLORA_DEFAULTS["lora_alpha"],
    lora_dropout: float = QLORA_DEFAULTS["lora_dropout"],
    # Training config overrides
    num_train_epochs: int = TRAINING_DEFAULTS["num_train_epochs"],
    learning_rate: float = TRAINING_DEFAULTS["learning_rate"],
    per_device_train_batch_size: int = TRAINING_DEFAULTS["per_device_train_batch_size"],
    gradient_accumulation_steps: int = TRAINING_DEFAULTS["gradient_accumulation_steps"],
    max_seq_length: int = TRAINING_DEFAULTS["max_seq_length"],
    warmup_ratio: float = TRAINING_DEFAULTS["warmup_ratio"],
    logging_steps: int = TRAINING_DEFAULTS["logging_steps"],
    save_steps: int = TRAINING_DEFAULTS["save_steps"],
    max_steps: int = 0,
    cancel_event: Optional[threading.Event] = None,
) -> TrainingResult:
    """
    Run a QLoRA fine-tuning job. SYNCHRONOUS - blocks until complete.

    This function is designed to run in a ThreadPoolExecutor so the async
    FastAPI event loop is not blocked (wired in Step 13).

    The SynthBoardTrainerCallback automatically pushes progress events to
    the SSE broadcast system via get_broadcaster(run_id).
    """
    start_time = time.time()
    checkpoint_dir = CHECKPOINTS_DIR / run_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    broadcaster = get_broadcaster(run_id)

    try:
        # ── 1. Pre-flight checks ──
        _check_gated_model(model_name)

        if model_name not in MODEL_TIERS:
            logger.warning(
                "Model '%s' not in MODEL_TIERS - proceeding anyway but VRAM limits unknown",
                model_name,
            )

        # ── 2. Load dataset ──
        logger.info("Loading dataset from %s", dataset_path)
        raw_samples = _load_formatted_dataset(dataset_path)
        num_samples = len(raw_samples)
        logger.info("Dataset loaded: %d samples", num_samples)

        # ── 3. Compute total steps ──
        total_steps = compute_total_steps(
            num_samples=num_samples,
            batch_size=per_device_train_batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            num_epochs=num_train_epochs,
            max_steps=max_steps,
        )
        logger.info("Total training steps: %d", total_steps)

        # ── 4. Load model + tokenizer via unsloth ──
        logger.info("Loading model: %s (4-bit, max_seq_length=%d)", model_name, max_seq_length)
        from unsloth import FastLanguageModel

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=model_name,
            max_seq_length=max_seq_length,
            load_in_4bit=True,
            dtype=None,  # auto-detect
        )
        logger.info("Model loaded successfully")

        # ── 5. Apply QLoRA adapters ──
        logger.info("Applying QLoRA adapters (r=%d, alpha=%d)", r, lora_alpha)
        model = FastLanguageModel.get_peft_model(
            model,
            r=r,
            lora_alpha=lora_alpha,
            lora_dropout=lora_dropout,
            target_modules=QLORA_DEFAULTS["target_modules"],
            bias="none",
            use_gradient_checkpointing="unsloth",
        )
        logger.info("QLoRA adapters applied")

        # ── 6. Prepare dataset ──
        logger.info("Building training dataset...")
        train_dataset = _build_dataset(raw_samples, tokenizer)
        logger.info("Training dataset ready: %d samples", len(train_dataset))

        # ── 7. Configure SFTTrainer ──
        from trl import SFTTrainer
        from transformers import TrainingArguments

        # Detect model dtype - unsloth loads some models in bf16
        model_dtype = getattr(model, "dtype", None)
        use_bf16 = (model_dtype == torch.bfloat16)
        use_fp16 = not use_bf16
        logger.info("Training precision: %s", "bf16" if use_bf16 else "fp16")

        # Compute warmup_steps from warmup_ratio (warmup_ratio deprecated in newer trl)
        warmup_steps = max(1, int(total_steps * warmup_ratio))

        training_args = TrainingArguments(
            output_dir=str(checkpoint_dir),
            per_device_train_batch_size=per_device_train_batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            num_train_epochs=num_train_epochs,
            learning_rate=learning_rate,
            warmup_steps=warmup_steps,
            lr_scheduler_type=TRAINING_DEFAULTS["lr_scheduler_type"],
            logging_steps=logging_steps,
            save_steps=save_steps,
            fp16=use_fp16,
            bf16=use_bf16,
            optim=TRAINING_DEFAULTS["optim"],
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            dataloader_num_workers=0,
            dataloader_pin_memory=False,
            max_steps=max_steps if max_steps > 0 else -1,
            report_to="none",
            save_total_limit=2,
        )

        # Create the SSE callback
        sse_callback = SynthBoardTrainerCallback(
            run_id=run_id,
            total_steps=total_steps,
            cancel_event=cancel_event,
            start_time=start_time,
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=train_dataset,
            args=training_args,
            dataset_text_field="text",
            max_seq_length=max_seq_length,
            packing=False,
            callbacks=[sse_callback],
        )

        # ── 8. Train ──
        logger.info("Starting training...")
        train_result = trainer.train()

        # Check if cancelled
        if cancel_event is not None and cancel_event.is_set():
            elapsed = time.time() - start_time
            return TrainingResult(
                success=False,
                run_id=run_id,
                total_time_seconds=round(elapsed, 1),
                error="Training cancelled by user.",
            )

        # Extract final loss from training history
        final_loss = None
        if train_result.metrics:
            final_loss = train_result.metrics.get("train_loss")

        # ── 9. Save final adapter ──
        final_checkpoint = str(checkpoint_dir / "final")
        trainer.save_model(final_checkpoint)
        tokenizer.save_pretrained(final_checkpoint)
        logger.info("Final adapter saved to %s", final_checkpoint)

        elapsed = time.time() - start_time
        logger.info(
            "Training complete: %d steps, loss=%.4f, time=%.1fs",
            total_steps, final_loss or 0.0, elapsed,
        )

        return TrainingResult(
            success=True,
            run_id=run_id,
            final_loss=final_loss,
            total_steps=total_steps,
            total_time_seconds=round(elapsed, 1),
            checkpoint_path=final_checkpoint,
        )

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("Training failed after %.1fs: %s", elapsed, e, exc_info=True)

        # Push error event to SSE subscribers
        broadcaster.push(TrainingEvent(
            event_type="error",
            data={"message": str(e)},
        ))

        return TrainingResult(
            success=False,
            run_id=run_id,
            total_time_seconds=round(elapsed, 1),
            error=str(e),
        )
    finally:
        # Free VRAM
        try:
            import gc
            if "model" in dir():
                del model
            if "trainer" in dir():
                del trainer
            gc.collect()
            torch.cuda.empty_cache()
            logger.info("VRAM cleared after training")
        except Exception:
            pass
