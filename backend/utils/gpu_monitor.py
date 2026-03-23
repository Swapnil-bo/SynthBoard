"""
GPU monitoring with fallback chain: pynvml → nvidia-smi CLI → null (with warning).
On native Windows, nvidia-smi.exe may be in C:\\Windows\\System32\\ — use full path as fallback.
"""
import logging
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Cached nvidia-smi path (set on first successful call)
_nvidia_smi_path: Optional[str] = None
_backend: Optional[str] = None  # "pynvml", "nvidia-smi", or "null"


@dataclass
class GpuStats:
    name: str
    vram_total_mb: int
    vram_used_mb: int
    vram_free_mb: int
    gpu_utilization_pct: int
    temperature_c: int
    driver_version: str


def _try_pynvml() -> Optional[GpuStats]:
    """Attempt to read GPU stats via pynvml."""
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        driver = pynvml.nvmlSystemGetDriverVersion()
        if isinstance(driver, bytes):
            driver = driver.decode("utf-8")
        pynvml.nvmlShutdown()
        return GpuStats(
            name=name,
            vram_total_mb=mem.total // (1024 * 1024),
            vram_used_mb=mem.used // (1024 * 1024),
            vram_free_mb=mem.free // (1024 * 1024),
            gpu_utilization_pct=util.gpu,
            temperature_c=temp,
            driver_version=driver,
        )
    except Exception as e:
        logger.debug("pynvml failed: %s", e)
        return None


def _find_nvidia_smi() -> Optional[str]:
    """Find a working nvidia-smi path. Cache result."""
    global _nvidia_smi_path
    if _nvidia_smi_path is not None:
        return _nvidia_smi_path

    candidates = [
        "nvidia-smi",  # In PATH
        r"C:\Windows\System32\nvidia-smi.exe",  # Windows full path
    ]
    for path in candidates:
        try:
            result = subprocess.run(
                [path, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                _nvidia_smi_path = path
                logger.info("nvidia-smi found at: %s", path)
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None


def _try_nvidia_smi() -> Optional[GpuStats]:
    """Attempt to read GPU stats via nvidia-smi CLI (XML output)."""
    path = _find_nvidia_smi()
    if path is None:
        return None
    try:
        result = subprocess.run(
            [path, "-q", "-x"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None

        root = ET.fromstring(result.stdout)
        gpu = root.find("gpu")
        if gpu is None:
            return None

        name = gpu.find("product_name").text or "Unknown"
        driver = root.find("driver_version").text or "Unknown"

        fb = gpu.find("fb_memory_usage")
        total_str = fb.find("total").text  # e.g. "6144 MiB"
        used_str = fb.find("used").text
        free_str = fb.find("free").text

        def parse_mib(s: str) -> int:
            return int(s.replace("MiB", "").strip())

        vram_total = parse_mib(total_str)
        vram_used = parse_mib(used_str)
        vram_free = parse_mib(free_str)

        util_elem = gpu.find("utilization")
        gpu_util_str = util_elem.find("gpu_util").text  # e.g. "42 %"
        gpu_util = int(gpu_util_str.replace("%", "").strip())

        temp_elem = gpu.find("temperature")
        temp_str = temp_elem.find("gpu_temp").text  # e.g. "55 C"
        temp = int(temp_str.replace("C", "").strip())

        return GpuStats(
            name=name,
            vram_total_mb=vram_total,
            vram_used_mb=vram_used,
            vram_free_mb=vram_free,
            gpu_utilization_pct=gpu_util,
            temperature_c=temp,
            driver_version=driver,
        )
    except Exception as e:
        logger.debug("nvidia-smi XML parse failed: %s", e)
        return None


def get_gpu_stats() -> Optional[GpuStats]:
    """
    Get GPU stats using fallback chain: pynvml → nvidia-smi CLI → None.
    Caches which backend works after the first successful call.
    """
    global _backend

    if _backend == "pynvml":
        return _try_pynvml()
    if _backend == "nvidia-smi":
        return _try_nvidia_smi()
    if _backend == "null":
        return None

    # First call — probe both
    stats = _try_pynvml()
    if stats is not None:
        _backend = "pynvml"
        logger.info("GPU monitor using pynvml backend")
        return stats

    stats = _try_nvidia_smi()
    if stats is not None:
        _backend = "nvidia-smi"
        logger.info("GPU monitor using nvidia-smi backend")
        return stats

    _backend = "null"
    logger.warning("No GPU monitoring available. pynvml and nvidia-smi both failed.")
    return None


def get_backend_name() -> str:
    """Return which monitoring backend is active."""
    if _backend is None:
        get_gpu_stats()  # trigger probe
    return _backend or "null"
