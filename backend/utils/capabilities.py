"""
Startup probe: checks availability of unsloth, bitsandbytes, CUDA, GGUF export, trl.
Results are cached at startup and served via /api/system/capabilities.
"""
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    """Cached result of the startup capability probe."""
    # CUDA / torch
    cuda_available: bool = False
    cuda_version: Optional[str] = None
    torch_version: Optional[str] = None
    gpu_name: Optional[str] = None
    vram_total_mb: Optional[int] = None

    # unsloth
    unsloth_available: bool = False
    unsloth_version: Optional[str] = None

    # bitsandbytes
    bitsandbytes_available: bool = False
    bitsandbytes_version: Optional[str] = None

    # trl / SFTTrainer
    trl_available: bool = False
    trl_version: Optional[str] = None

    # GGUF export method
    gguf_export_method: str = "unavailable"  # unsloth-native / llama-cpp-python / external-binary / unavailable

    # Warnings collected during probe
    warnings: list[str] = field(default_factory=list)


# Module-level cached result — populated once at startup
_probe: Optional[ProbeResult] = None


def _probe_torch(result: ProbeResult) -> None:
    """Check torch + CUDA availability."""
    try:
        import torch
        result.torch_version = torch.__version__
        result.cuda_available = torch.cuda.is_available()
        if result.cuda_available:
            result.cuda_version = torch.version.cuda
            result.gpu_name = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_memory
            result.vram_total_mb = vram_bytes // (1024 * 1024)
            logger.info(
                "CUDA OK: %s, VRAM %d MB, CUDA %s, torch %s",
                result.gpu_name, result.vram_total_mb,
                result.cuda_version, result.torch_version,
            )
        else:
            result.warnings.append("CUDA not available — torch.cuda.is_available() returned False")
            logger.warning("torch installed but CUDA not available")
    except ImportError:
        result.warnings.append("torch not installed")
        logger.error("torch not found")


def _probe_unsloth(result: ProbeResult) -> None:
    """Check unsloth availability."""
    try:
        import unsloth
        result.unsloth_available = True
        result.unsloth_version = getattr(unsloth, "__version__", "unknown")
        # Verify FastLanguageModel is importable
        from unsloth import FastLanguageModel  # noqa: F401
        logger.info("unsloth OK: version %s", result.unsloth_version)
    except ImportError as e:
        result.warnings.append(f"unsloth not available: {e}")
        logger.warning("unsloth import failed: %s", e)


def _probe_bitsandbytes(result: ProbeResult) -> None:
    """Check bitsandbytes availability."""
    try:
        import bitsandbytes
        result.bitsandbytes_available = True
        result.bitsandbytes_version = getattr(bitsandbytes, "__version__", "unknown")
        logger.info("bitsandbytes OK: version %s", result.bitsandbytes_version)
    except ImportError as e:
        result.warnings.append(f"bitsandbytes not available: {e}")
        logger.warning("bitsandbytes import failed: %s", e)


def _probe_trl(result: ProbeResult) -> None:
    """Check trl / SFTTrainer availability."""
    try:
        import trl
        result.trl_available = True
        result.trl_version = getattr(trl, "__version__", "unknown")
        from trl import SFTTrainer  # noqa: F401
        logger.info("trl OK: version %s (SFTTrainer available)", result.trl_version)
    except ImportError as e:
        result.warnings.append(f"trl/SFTTrainer not available: {e}")
        logger.warning("trl import failed: %s", e)


def _probe_gguf(result: ProbeResult) -> None:
    """Determine best available GGUF export method. Probe in priority order."""
    # Method 1: unsloth-native save_to_gguf
    try:
        from unsloth import save_to_gguf  # noqa: F401
        result.gguf_export_method = "unsloth-native"
        logger.info("GGUF export: unsloth-native (save_to_gguf)")
        return
    except ImportError:
        pass

    # Also check the older API name in case of version differences
    try:
        from unsloth import FastLanguageModel
        if hasattr(FastLanguageModel, "save_pretrained_gguf"):
            result.gguf_export_method = "unsloth-native"
            logger.info("GGUF export: unsloth-native (save_pretrained_gguf)")
            return
    except ImportError:
        pass

    # Method 2: llama-cpp-python
    try:
        import llama_cpp  # noqa: F401
        result.gguf_export_method = "llama-cpp-python"
        logger.info("GGUF export: llama-cpp-python")
        return
    except ImportError:
        pass

    # Method 3: external llama-quantize binary
    binary_name = "llama-quantize"
    if shutil.which(binary_name):
        result.gguf_export_method = "external-binary"
        logger.info("GGUF export: external-binary (llama-quantize in PATH)")
        return

    # Also check project-local bin
    try:
        from backend.config import PROJECT_ROOT
        local_bin = PROJECT_ROOT / "bin" / "llama-quantize.exe"
        if local_bin.exists():
            result.gguf_export_method = "external-binary"
            logger.info("GGUF export: external-binary (%s)", local_bin)
            return
    except Exception:
        pass

    result.gguf_export_method = "unavailable"
    result.warnings.append(
        "No GGUF export method available. Install unsloth (save_to_gguf), "
        "llama-cpp-python, or place llama-quantize binary in PATH."
    )
    logger.warning("No GGUF export method found")


def _check_flash_attention(result: ProbeResult) -> None:
    """Check if Flash Attention 2 is available (informational only)."""
    try:
        import flash_attn  # noqa: F401
        logger.info("Flash Attention 2 available")
    except ImportError:
        result.warnings.append("Flash Attention 2 not available - xformers or default attention will be used")
        logger.info("Flash Attention 2 not installed (xformers fallback is fine)")


def run_startup_probe() -> ProbeResult:
    """
    Run all capability probes. Call once at server startup.
    Results are cached and returned by get_capabilities().
    """
    global _probe
    logger.info("=== SynthBoard Startup Capability Probe ===")

    result = ProbeResult()
    _probe_torch(result)
    _probe_bitsandbytes(result)
    _probe_unsloth(result)
    _probe_trl(result)
    _probe_gguf(result)
    _check_flash_attention(result)

    ready = (
        result.cuda_available
        and result.unsloth_available
        and result.bitsandbytes_available
        and result.trl_available
    )
    if ready:
        logger.info("=== Probe complete: ALL core dependencies OK ===")
    else:
        logger.warning("=== Probe complete: some dependencies missing (see warnings) ===")

    _probe = result
    return result


def get_capabilities() -> ProbeResult:
    """Return cached probe result. Runs probe if not yet executed."""
    global _probe
    if _probe is None:
        return run_startup_probe()
    return _probe
