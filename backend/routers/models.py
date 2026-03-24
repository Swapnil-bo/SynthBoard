"""List models, export GGUF, register in Ollama."""
import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.config import DEFAULT_ELO, OLLAMA_BASE_URL
from backend.db.database import get_db
from backend.models.arena import (
    ArenaModelResponse,
    ExportRequest,
    ExportResponse,
    RegisterBaseModelRequest,
)
from backend.services.gguf_exporter import run_gguf_export

router = APIRouter(prefix="/api/models", tags=["models"])
logger = logging.getLogger(__name__)

# Export runs in a background thread (model loading + GGUF conversion is blocking)
_export_executor = ThreadPoolExecutor(max_workers=1)


def _row_to_arena_model(row) -> ArenaModelResponse:
    """Convert a DB row to an ArenaModelResponse."""
    return ArenaModelResponse(
        id=row["id"],
        name=row["name"],
        ollama_name=row["ollama_name"],
        source=row["source"],
        training_run_id=row["training_run_id"],
        elo_rating=row["elo_rating"],
        total_battles=row["total_battles"],
        total_wins=row["total_wins"],
        total_losses=row["total_losses"],
        total_ties=row["total_ties"],
        avg_ttft_ms=row["avg_ttft_ms"],
        avg_tps=row["avg_tps"],
        registered_at=row["registered_at"],
    )


# ---------------------------------------------------------------------------
# GET /api/models — list all arena models
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ArenaModelResponse])
async def list_models():
    """List all arena models (base + fine-tuned), ordered by Elo rating."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM arena_models ORDER BY elo_rating DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_arena_model(row) for row in rows]
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# POST /api/models/register-base — register a base Ollama model for arena
# ---------------------------------------------------------------------------

@router.post("/register-base", response_model=ArenaModelResponse, status_code=201)
async def register_base_model(request: RegisterBaseModelRequest):
    """Register a base Ollama model for use in the arena."""
    model_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()
    try:
        # Check if already registered with same ollama_name
        cursor = await db.execute(
            "SELECT id FROM arena_models WHERE ollama_name = ?",
            (request.ollama_name,),
        )
        existing = await cursor.fetchone()
        if existing:
            raise HTTPException(
                409,
                f"Model with Ollama name '{request.ollama_name}' is already registered "
                f"(id: {existing['id']}).",
            )

        await db.execute(
            """INSERT INTO arena_models
               (id, name, ollama_name, source, elo_rating, total_battles,
                total_wins, total_losses, total_ties, registered_at)
               VALUES (?, ?, ?, 'base', ?, 0, 0, 0, 0, ?)""",
            (model_id, request.name, request.ollama_name, DEFAULT_ELO, now),
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM arena_models WHERE id = ?", (model_id,)
        )
        row = await cursor.fetchone()
        return _row_to_arena_model(row)
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# POST /api/models/export/{run_id} — export training run to GGUF + register
# ---------------------------------------------------------------------------

@router.post("/export/{run_id}", response_model=ExportResponse)
async def export_model(run_id: str, request: ExportRequest = None):
    """
    Export a completed training run to GGUF format and register in Ollama + arena.

    Steps:
    1. Validate run exists and is completed with a checkpoint
    2. Run GGUF export pipeline (blocking, in thread pool)
    3. Update training_runs table with gguf_path and ollama_model_name
    4. Register in arena_models table
    """
    if request is None:
        request = ExportRequest()

    # ── 1. Validate training run ──
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM training_runs WHERE id = ?", (run_id,)
        )
        run_row = await cursor.fetchone()
    finally:
        await db.close()

    if not run_row:
        raise HTTPException(404, f"Training run '{run_id}' not found.")
    if run_row["status"] != "completed":
        raise HTTPException(
            400,
            f"Training run '{run_id}' is not completed (status: {run_row['status']}). "
            f"Only completed runs can be exported.",
        )
    if not run_row["checkpoint_path"]:
        raise HTTPException(
            400,
            f"Training run '{run_id}' has no checkpoint path. Cannot export.",
        )
    if run_row["gguf_path"]:
        raise HTTPException(
            409,
            f"Training run '{run_id}' has already been exported to GGUF: "
            f"{run_row['gguf_path']}",
        )

    base_model = run_row["base_model"]
    checkpoint_path = run_row["checkpoint_path"]

    # ── 2. Run GGUF export in thread pool ──
    logger.info("Starting GGUF export for run %s (model: %s)", run_id, base_model)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _export_executor,
        run_gguf_export,
        run_id,
        base_model,
        checkpoint_path,
        request.quantization_method,
    )

    if not result.success:
        raise HTTPException(500, f"GGUF export failed: {result.error}")

    # ── 3. Update training_runs table ──
    db = await get_db()
    try:
        await db.execute(
            "UPDATE training_runs SET gguf_path = ?, ollama_model_name = ? WHERE id = ?",
            (result.gguf_path, result.ollama_model_name, run_id),
        )
        await db.commit()
    finally:
        await db.close()

    # ── 4. Register in arena_models table ──
    arena_model_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    short_model = base_model.split("/")[-1]
    display_name = f"{short_model} (fine-tuned, {run_id})"

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO arena_models
               (id, name, ollama_name, source, training_run_id, elo_rating,
                total_battles, total_wins, total_losses, total_ties, registered_at)
               VALUES (?, ?, ?, 'fine-tuned', ?, ?, 0, 0, 0, 0, ?)""",
            (arena_model_id, display_name, result.ollama_model_name,
             run_id, DEFAULT_ELO, now),
        )
        await db.commit()
    finally:
        await db.close()

    logger.info(
        "Export complete: run %s -> arena model %s (%s)",
        run_id, arena_model_id, result.ollama_model_name,
    )

    return ExportResponse(
        success=True,
        run_id=run_id,
        gguf_path=result.gguf_path,
        ollama_model_name=result.ollama_model_name,
        arena_model_id=arena_model_id,
        total_time_seconds=result.total_time_seconds,
    )


# ---------------------------------------------------------------------------
# DELETE /api/models/{id} — remove from arena
# ---------------------------------------------------------------------------

@router.delete("/{model_id}")
async def delete_model(model_id: str):
    """Remove a model from the arena."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, name FROM arena_models WHERE id = ?", (model_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, f"Arena model '{model_id}' not found.")

        await db.execute("DELETE FROM arena_models WHERE id = ?", (model_id,))
        await db.commit()

        return {"message": f"Model '{row['name']}' removed from arena."}
    finally:
        await db.close()
