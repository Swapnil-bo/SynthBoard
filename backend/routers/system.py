"""System endpoints: GPU stats, health check, disk usage."""
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter

from backend.config import (
    CHECKPOINTS_DIR,
    DATABASE_PATH,
    EXPORTS_DIR,
    FORMATTED_DIR,
    GATED_MODELS,
    MODEL_TIERS,
    OLLAMA_BASE_URL,
    UPLOADS_DIR,
)
from backend.db.database import get_db
from backend.models.system import (
    CapabilitiesResponse,
    DiskCategory,
    DiskUsageResponse,
    GpuStatsResponse,
    HealthResponse,
    ModelTierInfo,
)
from backend.utils.capabilities import get_capabilities
from backend.utils.gpu_monitor import get_backend_name, get_gpu_stats

router = APIRouter(prefix="/api/system", tags=["system"])


def _dir_stats(path: Path) -> DiskCategory:
    """Calculate total size and file count for a directory."""
    total = 0
    count = 0
    if path.exists():
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
                count += 1
    return DiskCategory(
        path=str(path),
        size_mb=round(total / (1024 * 1024), 2),
        file_count=count,
    )


@router.get("/gpu", response_model=GpuStatsResponse)
async def gpu_stats():
    """Current GPU utilization, VRAM, temperature."""
    stats = get_gpu_stats()
    if stats is None:
        return GpuStatsResponse(
            available=False,
            backend=get_backend_name(),
            warning="No GPU monitoring available. Install pynvml or ensure nvidia-smi is accessible.",
        )
    return GpuStatsResponse(
        available=True,
        backend=get_backend_name(),
        name=stats.name,
        vram_total_mb=stats.vram_total_mb,
        vram_used_mb=stats.vram_used_mb,
        vram_free_mb=stats.vram_free_mb,
        gpu_utilization_pct=stats.gpu_utilization_pct,
        temperature_c=stats.temperature_c,
        driver_version=stats.driver_version,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Ollama running status, disk space, active training status."""
    warnings: list[str] = []

    # Check Ollama
    ollama_running = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_running = resp.status_code == 200
    except Exception:
        warnings.append("Ollama is not running or not reachable.")

    # Check GPU
    gpu_available = get_gpu_stats() is not None
    if not gpu_available:
        warnings.append("GPU monitoring unavailable.")

    # Check active training
    training_active = False
    active_run_id = None
    db_ok = True
    try:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT id FROM training_runs WHERE status = 'running' LIMIT 1"
            )
            row = await cursor.fetchone()
            if row:
                training_active = True
                active_run_id = row[0]
        finally:
            await db.close()
    except Exception as e:
        db_ok = False
        warnings.append(f"Database error: {e}")

    # Check disk space
    disk_free_mb = 0.0
    try:
        usage = shutil.disk_usage(DATABASE_PATH.parent)
        disk_free_mb = round(usage.free / (1024 * 1024), 2)
        if disk_free_mb < 5000:
            warnings.append(f"Low disk space: {disk_free_mb:.0f} MB free.")
    except Exception:
        warnings.append("Could not determine disk free space.")

    status = "ok" if (not warnings or (len(warnings) == 1 and not ollama_running)) else "degraded"
    # Ollama not running alone is a warning, not degraded — it's optional until arena
    if not db_ok or not gpu_available:
        status = "degraded"

    return HealthResponse(
        status=status,
        ollama_running=ollama_running,
        ollama_url=OLLAMA_BASE_URL,
        gpu_available=gpu_available,
        training_active=training_active,
        active_training_run_id=active_run_id,
        disk_free_mb=disk_free_mb,
        database_ok=db_ok,
        warnings=warnings,
    )


@router.get("/disk", response_model=DiskUsageResponse)
async def disk_usage():
    """Breakdown of space used by checkpoints, GGUFs, datasets, uploads."""
    uploads = _dir_stats(UPLOADS_DIR)
    formatted = _dir_stats(FORMATTED_DIR)
    checkpoints = _dir_stats(CHECKPOINTS_DIR)
    exports = _dir_stats(EXPORTS_DIR)

    db_mb = 0.0
    if DATABASE_PATH.exists():
        db_mb = round(DATABASE_PATH.stat().st_size / (1024 * 1024), 2)

    total = uploads.size_mb + formatted.size_mb + checkpoints.size_mb + exports.size_mb + db_mb

    return DiskUsageResponse(
        uploads=uploads,
        formatted=formatted,
        checkpoints=checkpoints,
        exports=exports,
        database_mb=db_mb,
        total_mb=round(total, 2),
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities():
    """Report hardware capabilities, available models, and dependency status."""
    probe = get_capabilities()

    # Build model tier list from config, marking gated models
    model_tiers = []
    for model_id, info in MODEL_TIERS.items():
        model_tiers.append(
            ModelTierInfo(
                model_id=model_id,
                tier=info["tier"],
                params=info["params"],
                vram_train_mb=info["vram_train_mb"],
                family=info["family"],
                gated=any(gated in model_id for gated in ["Llama"]),
            )
        )
    # Sort: tier 1 first, then by VRAM
    model_tiers.sort(key=lambda m: (m.tier, m.vram_train_mb))

    training_ready = (
        probe.cuda_available
        and probe.unsloth_available
        and probe.bitsandbytes_available
        and probe.trl_available
    )

    return CapabilitiesResponse(
        cuda_available=probe.cuda_available,
        cuda_version=probe.cuda_version,
        torch_version=probe.torch_version,
        gpu_name=probe.gpu_name,
        vram_total_mb=probe.vram_total_mb,
        unsloth_available=probe.unsloth_available,
        unsloth_version=probe.unsloth_version,
        bitsandbytes_available=probe.bitsandbytes_available,
        bitsandbytes_version=probe.bitsandbytes_version,
        trl_available=probe.trl_available,
        trl_version=probe.trl_version,
        gguf_export_method=probe.gguf_export_method,
        available_model_tiers=model_tiers,
        training_ready=training_ready,
        warnings=probe.warnings,
    )
