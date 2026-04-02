"""Ollama lifecycle — load/unload/list models and check service health."""
import logging

import httpx

from backend.config import OLLAMA_BASE_URL, OLLAMA_INFERENCE_TIMEOUT_S

logger = logging.getLogger(__name__)


async def check_ollama_running() -> bool:
    """Return True if Ollama is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


async def list_ollama_models() -> list[str]:
    """Return list of model names currently available in Ollama."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
        logger.warning("Failed to list Ollama models: %s", e)
        return []


async def unload_model(model_name: str) -> None:
    """Unload a model from Ollama VRAM by setting keep_alive=0."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "",
                    "keep_alive": 0,
                },
            )
            if resp.status_code == 200:
                logger.info("Unloaded model %s from VRAM", model_name)
            else:
                logger.warning(
                    "Unload request for %s returned status %d",
                    model_name, resp.status_code,
                )
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning("Failed to unload model %s: %s", model_name, e)
