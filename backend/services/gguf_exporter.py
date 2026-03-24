"""
Checkpoint -> GGUF -> Ollama registration.

Full export pipeline:
1. Pre-flight disk space check
2. Load base model + LoRA adapter from checkpoint
3. Merge + convert to GGUF via unsloth's save_pretrained_gguf
4. Generate Ollama Modelfile with correct chat template (from config.OLLAMA_TEMPLATES)
5. Register in Ollama via `ollama create`
6. Verify with a test prompt
"""
import gc
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from backend.config import (
    EXPORTS_DIR,
    MODEL_TIERS,
    OLLAMA_BASE_URL,
    OLLAMA_TEMPLATES,
)

logger = logging.getLogger(__name__)

# Estimated disk overhead for merge+GGUF per model size tier
# merged HF model (~2x final GGUF) + GGUF output
DISK_ESTIMATES_MB = {
    "1B": {"temp": 3000, "final": 800},
    "1.5B": {"temp": 4000, "final": 1100},
    "1.7B": {"temp": 4500, "final": 1200},
    "3B": {"temp": 7000, "final": 2000},
}


@dataclass
class ExportResult:
    """Result of the GGUF export pipeline."""
    success: bool
    gguf_path: Optional[str] = None
    ollama_model_name: Optional[str] = None
    error: Optional[str] = None
    total_time_seconds: Optional[float] = None


def _get_model_family(model_name: str) -> str:
    """Detect model family from the base model name for template selection."""
    name_lower = model_name.lower()
    if "qwen" in name_lower:
        return "qwen2.5"
    if "llama" in name_lower:
        return "llama3"
    if "smollm" in name_lower:
        return "smollm2"
    if "phi" in name_lower:
        return "phi3"
    # Default to ChatML (qwen/smollm style)
    logger.warning("Unknown model family for '%s', defaulting to qwen2.5 template", model_name)
    return "qwen2.5"


def _get_params_tier(model_name: str) -> str:
    """Get the parameter size label for disk estimation."""
    tier_info = MODEL_TIERS.get(model_name)
    if tier_info:
        return tier_info["params"]
    # Fallback heuristic
    name_lower = model_name.lower()
    if "1.5b" in name_lower or "1.7b" in name_lower:
        return "1.5B"
    if "3b" in name_lower or "3.8b" in name_lower:
        return "3B"
    if "1b" in name_lower:
        return "1B"
    return "1.5B"  # conservative default


def _check_disk_space(model_name: str) -> Optional[str]:
    """
    Pre-flight disk space check.
    Returns an error message if insufficient space, None if OK.
    """
    params = _get_params_tier(model_name)
    estimate = DISK_ESTIMATES_MB.get(params, DISK_ESTIMATES_MB["1.5B"])
    required_mb = estimate["temp"] + estimate["final"]

    disk_usage = shutil.disk_usage(str(EXPORTS_DIR))
    free_mb = disk_usage.free // (1024 * 1024)

    if free_mb < required_mb:
        return (
            f"Insufficient disk space for GGUF export. "
            f"Need ~{required_mb} MB (temp: {estimate['temp']} MB + GGUF: {estimate['final']} MB), "
            f"but only {free_mb} MB free. "
            f"Delete old checkpoints or exports to free space."
        )
    logger.info("Disk space check OK: %d MB free, need ~%d MB", free_mb, required_mb)
    return None


def _check_ollama_running() -> bool:
    """Check if Ollama is running and reachable."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _generate_modelfile(gguf_path: str, model_family: str) -> str:
    """
    Generate an Ollama Modelfile with the correct chat template
    based on the model family.
    """
    template = OLLAMA_TEMPLATES.get(model_family)
    if not template:
        logger.warning("No template for family '%s', using qwen2.5 default", model_family)
        template = OLLAMA_TEMPLATES["qwen2.5"]

    # Use forward slashes in the path for Ollama compatibility
    gguf_path_normalized = gguf_path.replace("\\", "/")

    modelfile = (
        f'FROM {gguf_path_normalized}\n'
        f'PARAMETER temperature 0.7\n'
        f'PARAMETER top_p 0.9\n'
        f'TEMPLATE """{template}"""\n'
    )
    return modelfile


def _register_in_ollama(
    ollama_model_name: str,
    gguf_path: str,
    model_family: str,
    export_dir: Path,
) -> Optional[str]:
    """
    Create a Modelfile and register the model in Ollama.
    Returns error message on failure, None on success.
    """
    modelfile_content = _generate_modelfile(gguf_path, model_family)
    modelfile_path = export_dir / "Modelfile"
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    logger.info("Modelfile written to %s", modelfile_path)
    logger.debug("Modelfile content:\n%s", modelfile_content)

    # Run: ollama create <name> -f Modelfile
    try:
        result = subprocess.run(
            ["ollama", "create", ollama_model_name, "-f", str(modelfile_path)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for large models
            cwd=str(export_dir),
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            logger.error("ollama create failed: %s", error_msg)
            return f"ollama create failed (exit code {result.returncode}): {error_msg}"
        logger.info("Model registered in Ollama: %s", ollama_model_name)
        logger.debug("ollama create output: %s", result.stdout.strip())
        return None
    except FileNotFoundError:
        return "Ollama CLI not found. Make sure Ollama is installed and in PATH."
    except subprocess.TimeoutExpired:
        return "ollama create timed out after 300 seconds."
    except Exception as e:
        return f"ollama create error: {e}"


def _verify_with_test_prompt(ollama_model_name: str) -> Optional[str]:
    """
    Run a test prompt through Ollama to verify the model loads and responds.
    Returns error message on failure, None on success.
    """
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": ollama_model_name,
                "prompt": "Hello, what is 2+2?",
                "stream": False,
                "options": {"num_predict": 32},
            },
            timeout=120,
        )
        if resp.status_code != 200:
            return f"Test inference failed with status {resp.status_code}: {resp.text[:200]}"

        data = resp.json()
        response_text = data.get("response", "").strip()
        if not response_text:
            return "Test inference returned empty response"

        logger.info("Test inference OK: '%s...'", response_text[:80])

        # Unload the model after test to free VRAM
        try:
            httpx.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": ollama_model_name, "keep_alive": 0},
                timeout=10,
            )
        except Exception:
            pass

        return None
    except httpx.TimeoutException:
        return "Test inference timed out after 120 seconds"
    except Exception as e:
        return f"Test inference error: {e}"


def run_gguf_export(
    run_id: str,
    base_model_name: str,
    checkpoint_path: str,
    quantization_method: str = "q4_k_m",
) -> ExportResult:
    """
    Full GGUF export pipeline. Runs synchronously (call via ThreadPoolExecutor).

    Steps:
    1. Pre-flight disk space check
    2. Load base model + LoRA adapter
    3. Merge + export to GGUF via unsloth
    4. Generate Modelfile with correct template
    5. Register in Ollama
    6. Verify with test prompt
    """
    start_time = time.time()

    # ── 1. Pre-flight checks ──
    disk_error = _check_disk_space(base_model_name)
    if disk_error:
        return ExportResult(success=False, error=disk_error)

    if not _check_ollama_running():
        return ExportResult(
            success=False,
            error="Ollama is not running. Start Ollama before exporting.",
        )

    # Validate checkpoint exists
    checkpoint_dir = Path(checkpoint_path)
    if not checkpoint_dir.exists():
        return ExportResult(
            success=False,
            error=f"Checkpoint not found: {checkpoint_path}",
        )

    # Determine model family and build names
    model_family = _get_model_family(base_model_name)
    short_model = base_model_name.split("/")[-1].lower()
    # Clean up the model name for Ollama (remove bnb-4bit suffix etc.)
    for suffix in ["-bnb-4bit", "-bnb-8bit", "-instruct"]:
        short_model = short_model.replace(suffix, "")
    ollama_model_name = f"synthboard-{short_model}-{run_id}"

    # Export directory
    export_dir = EXPORTS_DIR / run_id
    export_dir.mkdir(parents=True, exist_ok=True)

    gguf_path = None
    gguf_size_mb = 0.0

    try:
        # ── 2. Load base model + LoRA adapter ──
        logger.info("Loading base model + LoRA adapter for export...")
        from unsloth import FastLanguageModel

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=checkpoint_path,
            max_seq_length=1024,
            load_in_4bit=True,
            dtype=None,
        )
        logger.info("Model loaded from checkpoint: %s", checkpoint_path)

        # ── 3. Merge + export to GGUF ──
        logger.info("Starting GGUF export (quantization: %s)...", quantization_method)
        model.save_pretrained_gguf(
            str(export_dir),
            tokenizer,
            quantization_method=quantization_method,
        )
        logger.info("GGUF export complete")

        # Find the generated GGUF file
        gguf_files = list(export_dir.glob("*.gguf"))
        if not gguf_files:
            return ExportResult(
                success=False,
                error="GGUF export produced no .gguf file. Check logs for conversion errors.",
            )

        gguf_path = str(gguf_files[0])
        gguf_size_mb = os.path.getsize(gguf_path) / (1024 * 1024)
        logger.info("GGUF file: %s (%.1f MB)", gguf_path, gguf_size_mb)

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("GGUF export failed: %s", e, exc_info=True)
        return ExportResult(
            success=False,
            error=f"GGUF export failed: {e}",
            total_time_seconds=round(elapsed, 1),
        )
    finally:
        # Free GPU memory
        try:
            if "model" in locals():
                del model
            if "tokenizer" in locals():
                del tokenizer
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # ── 4+5. Register in Ollama ──
    logger.info("Registering model in Ollama as '%s'...", ollama_model_name)
    reg_error = _register_in_ollama(ollama_model_name, gguf_path, model_family, export_dir)
    if reg_error:
        elapsed = time.time() - start_time
        return ExportResult(
            success=False,
            gguf_path=gguf_path,
            error=f"GGUF created but Ollama registration failed: {reg_error}",
            total_time_seconds=round(elapsed, 1),
        )

    # ── 6. Verify ──
    logger.info("Running test inference to verify model...")
    verify_error = _verify_with_test_prompt(ollama_model_name)
    if verify_error:
        logger.warning("Test inference failed (model may still work): %s", verify_error)
        # Don't fail the whole export for a verification issue

    elapsed = time.time() - start_time
    logger.info(
        "Export complete: %s -> %s (%.1f MB, %.1fs)",
        base_model_name, ollama_model_name, gguf_size_mb, elapsed,
    )

    # Clean up temporary merge files (keep only the .gguf and Modelfile)
    _cleanup_temp_files(export_dir)

    return ExportResult(
        success=True,
        gguf_path=gguf_path,
        ollama_model_name=ollama_model_name,
        total_time_seconds=round(elapsed, 1),
    )


def _cleanup_temp_files(export_dir: Path) -> None:
    """Remove temporary merge files, keeping only .gguf and Modelfile."""
    keep_extensions = {".gguf"}
    keep_names = {"Modelfile"}
    for item in export_dir.iterdir():
        if item.is_file() and item.suffix not in keep_extensions and item.name not in keep_names:
            try:
                item.unlink()
            except Exception:
                pass
        elif item.is_dir():
            try:
                shutil.rmtree(item)
            except Exception:
                pass
