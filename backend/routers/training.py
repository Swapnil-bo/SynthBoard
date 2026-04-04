"""Fine-tune launch, progress SSE, cancel, logs."""
import asyncio
import json
import logging
import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

import shutil

from backend.config import CHECKPOINTS_DIR, MODEL_TIERS, VRAM_SAFETY_MARGIN_MB
from backend.db.database import get_db
from backend.models.training import TrainingRequest, TrainingRunResponse
from backend.services.training_broadcaster import get_broadcaster, remove_broadcaster
from backend.services.training_engine import TrainingResult, compute_total_steps, run_training
from backend.utils.gpu_monitor import get_gpu_stats

router = APIRouter(prefix="/api/training", tags=["training"])
logger = logging.getLogger(__name__)

# Only 1 concurrent training — VRAM can't handle more
_training_executor = ThreadPoolExecutor(max_workers=1)

# Cancel events keyed by run_id
_cancel_events: dict[str, threading.Event] = {}

# SSE poll interval: how often to check the queue (seconds)
SSE_POLL_INTERVAL = 0.25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_active_run() -> dict | None:
    """Return the currently running training run, or None."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, base_model FROM training_runs WHERE status = 'running' LIMIT 1"
        )
        row = await cursor.fetchone()
        if row:
            return {"id": row["id"], "base_model": row["base_model"]}
        return None
    finally:
        await db.close()


async def _update_run_status(
    run_id: str,
    status: str,
    final_loss: float | None = None,
    checkpoint_path: str | None = None,
):
    """Update a training run's status and optional fields in the DB."""
    db = await get_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        if status in ("completed", "failed", "cancelled"):
            await db.execute(
                """UPDATE training_runs
                   SET status = ?, final_loss = ?, checkpoint_path = ?, completed_at = ?
                   WHERE id = ?""",
                (status, final_loss, checkpoint_path, now, run_id),
            )
        else:
            await db.execute(
                "UPDATE training_runs SET status = ?, started_at = ? WHERE id = ?",
                (status, now, run_id),
            )
        await db.commit()
    finally:
        await db.close()


def _row_to_response(row) -> TrainingRunResponse:
    """Convert a DB row to a TrainingRunResponse."""
    config_raw = row["config"]
    config = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
    return TrainingRunResponse(
        id=row["id"],
        base_model=row["base_model"],
        dataset_id=row["dataset_id"],
        config=config,
        status=row["status"],
        final_loss=row["final_loss"],
        total_steps=row["total_steps"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        checkpoint_path=row["checkpoint_path"],
        gguf_path=row["gguf_path"],
        ollama_model_name=row["ollama_model_name"],
    )


# ---------------------------------------------------------------------------
# POST /api/training/start
# ---------------------------------------------------------------------------

@router.post("/start", response_model=TrainingRunResponse, status_code=202)
async def start_training(request: TrainingRequest):
    """
    Launch a fine-tuning run.

    Pre-flight checks:
    1. Global training lock - only one run at a time
    2. Dataset exists and is formatted
    3. VRAM guard - enough free VRAM for the selected model
    """
    # ── 1. Global training lock ──
    active = await _get_active_run()
    if active:
        raise HTTPException(
            409,
            f"Training run '{active['id']}' is already active "
            f"(model: {active['base_model']}). Cancel it first.",
        )

    # ── 2. Validate dataset exists and has a formatted_path ──
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, formatted_path, num_samples FROM datasets WHERE id = ?",
            (request.dataset_id,),
        )
        ds_row = await cursor.fetchone()
    finally:
        await db.close()

    if not ds_row:
        raise HTTPException(404, f"Dataset '{request.dataset_id}' not found.")
    if not ds_row["formatted_path"]:
        raise HTTPException(
            400,
            f"Dataset '{request.dataset_id}' has not been formatted yet. "
            f"Call POST /api/datasets/{request.dataset_id}/format first.",
        )

    dataset_path = ds_row["formatted_path"]
    num_samples = ds_row["num_samples"] or 0

    # ── 3. VRAM guard ──
    tier_info = MODEL_TIERS.get(request.model_name)
    if tier_info:
        estimated_vram = tier_info["vram_train_mb"]
        gpu_stats = get_gpu_stats()
        if gpu_stats:
            free_vram = gpu_stats.vram_free_mb
            if estimated_vram > (free_vram - VRAM_SAFETY_MARGIN_MB):
                raise HTTPException(
                    400,
                    f"Insufficient VRAM. Model '{request.model_name}' needs ~{estimated_vram} MB, "
                    f"but only {free_vram} MB free ({VRAM_SAFETY_MARGIN_MB} MB safety margin). "
                    f"Close other GPU applications or choose a smaller model.",
                )

    # ── 4. Compute total_steps ──
    total_steps = compute_total_steps(
        num_samples=num_samples,
        batch_size=request.per_device_train_batch_size,
        gradient_accumulation_steps=request.gradient_accumulation_steps,
        num_epochs=request.num_train_epochs,
        max_steps=request.max_steps,
    )

    # ── 5. Create run record in DB ──
    run_id = uuid.uuid4().hex[:12]
    config = {
        "r": request.r,
        "lora_alpha": request.lora_alpha,
        "lora_dropout": request.lora_dropout,
        "num_train_epochs": request.num_train_epochs,
        "learning_rate": request.learning_rate,
        "per_device_train_batch_size": request.per_device_train_batch_size,
        "gradient_accumulation_steps": request.gradient_accumulation_steps,
        "max_seq_length": request.max_seq_length,
        "warmup_ratio": request.warmup_ratio,
        "logging_steps": request.logging_steps,
        "save_steps": request.save_steps,
        "max_steps": request.max_steps,
    }

    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO training_runs
               (id, base_model, dataset_id, config, status, total_steps, started_at)
               VALUES (?, ?, ?, ?, 'running', ?, ?)""",
            (run_id, request.model_name, request.dataset_id,
             json.dumps(config), total_steps, now),
        )
        await db.commit()
    finally:
        await db.close()

    # ── 6. Create cancel event and launch training in background thread ──
    cancel_event = threading.Event()
    _cancel_events[run_id] = cancel_event

    loop = asyncio.get_event_loop()

    async def _on_training_done(result: TrainingResult):
        """Called when training thread completes. Updates DB."""
        _cancel_events.pop(run_id, None)

        if result.success:
            await _update_run_status(
                run_id, "completed",
                final_loss=result.final_loss,
                checkpoint_path=result.checkpoint_path,
            )
            logger.info("Run %s completed: loss=%.4f", run_id, result.final_loss or 0)
        elif result.error and "cancelled" in result.error.lower():
            await _update_run_status(run_id, "cancelled")
            # Delete partial checkpoints on cancel
            ckpt_dir = CHECKPOINTS_DIR / run_id
            if ckpt_dir.exists():
                try:
                    shutil.rmtree(ckpt_dir)
                    logger.info("Deleted partial checkpoints for cancelled run %s", run_id)
                except Exception as cleanup_err:
                    logger.warning("Failed to clean up checkpoints for %s: %s", run_id, cleanup_err)
            logger.info("Run %s cancelled", run_id)
        else:
            await _update_run_status(run_id, "failed")
            logger.error("Run %s failed: %s", run_id, result.error)

    def _run_and_callback():
        """Runs training synchronously, then schedules async DB update."""
        result = run_training(
            run_id=run_id,
            model_name=request.model_name,
            dataset_path=dataset_path,
            r=request.r,
            lora_alpha=request.lora_alpha,
            lora_dropout=request.lora_dropout,
            num_train_epochs=request.num_train_epochs,
            learning_rate=request.learning_rate,
            per_device_train_batch_size=request.per_device_train_batch_size,
            gradient_accumulation_steps=request.gradient_accumulation_steps,
            max_seq_length=request.max_seq_length,
            warmup_ratio=request.warmup_ratio,
            logging_steps=request.logging_steps,
            save_steps=request.save_steps,
            max_steps=request.max_steps,
            cancel_event=cancel_event,
        )
        # Schedule the async DB update back on the event loop
        asyncio.run_coroutine_threadsafe(_on_training_done(result), loop)

    _training_executor.submit(_run_and_callback)
    logger.info("Training run %s submitted (model=%s, dataset=%s, steps=%d)",
                run_id, request.model_name, request.dataset_id, total_steps)

    # ── 7. Return the run record ──
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM training_runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /api/training/runs
# ---------------------------------------------------------------------------

@router.get("/runs", response_model=list[TrainingRunResponse])
async def list_runs():
    """List all training runs, newest first."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM training_runs ORDER BY started_at DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_response(row) for row in rows]
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# GET /api/training/runs/{id}
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}", response_model=TrainingRunResponse)
async def get_run(run_id: str):
    """Get details for a single training run."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM training_runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if not row:
        raise HTTPException(404, f"Training run '{run_id}' not found.")
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /api/training/runs/{id}/stream  (SSE — implemented in Step 12)
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}/stream")
async def training_stream(run_id: str, request: Request):
    """
    SSE stream of training progress for a given run.

    Each connected client gets its own subscriber queue (broadcast pattern).
    The TrainerCallback pushes events to all subscriber queues from the
    training thread. This endpoint reads from the client's queue and
    yields SSE-formatted events.

    On client disconnect, the subscriber queue is deregistered to prevent
    memory leaks.
    """
    broadcaster = get_broadcaster(run_id)
    subscriber_queue = broadcaster.subscribe()

    async def event_generator():
        try:
            while True:
                # Check if the client has disconnected
                if await request.is_disconnected():
                    logger.debug("SSE client disconnected for run %s", run_id)
                    break

                # Non-blocking read from the queue
                try:
                    event = subscriber_queue.get_nowait()
                    yield event.to_sse()

                    # If this was a terminal event, break after sending
                    if event.event_type in ("complete", "error", "cancelled"):
                        break
                except queue.Empty:
                    # No events available, send a keepalive comment to prevent
                    # proxy/browser timeouts, then wait
                    yield ": keepalive\n\n"
                    await asyncio.sleep(SSE_POLL_INTERVAL)

        finally:
            broadcaster.unsubscribe(subscriber_queue)
            logger.debug("SSE subscriber cleaned up for run %s", run_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# POST /api/training/runs/{id}/cancel
# ---------------------------------------------------------------------------

@router.post("/runs/{run_id}/cancel")
async def cancel_training(run_id: str):
    """Cancel a running training job."""
    # Check the run exists and is running
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, status FROM training_runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if not row:
        raise HTTPException(404, f"Training run '{run_id}' not found.")
    if row["status"] != "running":
        raise HTTPException(
            400,
            f"Training run '{run_id}' is not running (status: {row['status']}).",
        )

    # Signal cancellation
    cancel_event = _cancel_events.get(run_id)
    if cancel_event:
        cancel_event.set()
        logger.info("Cancel signal sent to training run %s", run_id)
        return {"message": f"Cancel signal sent to run '{run_id}'. Training will stop after the current step."}

    # Cancel event missing — training may have already finished between checks
    raise HTTPException(400, f"No active cancel handle for run '{run_id}'. It may have already finished.")
