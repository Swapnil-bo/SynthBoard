"""
Sequential inference engine for the arena.

Loads Model A -> generates -> unloads -> loads Model B -> generates -> unloads.
NEVER loads two models simultaneously (VRAM constraint on RTX 3050 6GB).
"""
import json
import logging
import random
import time

import httpx

from backend.config import OLLAMA_BASE_URL, OLLAMA_INFERENCE_TIMEOUT_S, PROMPT_BANK_PATH
from backend.db.database import get_db
from backend.services.model_manager import check_ollama_running, unload_model

logger = logging.getLogger(__name__)


def load_prompt_bank() -> list[dict]:
    """Load prompts from the prompt bank JSON file."""
    try:
        with open(PROMPT_BANK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("prompts", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to load prompt bank: %s", e)
        return []


def get_random_prompt() -> tuple[str, str | None]:
    """Return (prompt_text, category) from the bank, or raise if empty."""
    prompts = load_prompt_bank()
    if not prompts:
        raise ValueError("Prompt bank is empty or missing.")
    entry = random.choice(prompts)
    return entry["prompt"], entry.get("category")


async def select_battle_models() -> tuple[dict, dict]:
    """
    Randomly pick 2 distinct models from arena_models.
    Returns (model_a_row, model_b_row) with random position assignment.
    Raises ValueError if fewer than 2 models registered.
    """
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM arena_models")
        rows = await cursor.fetchall()
    finally:
        await db.close()

    if len(rows) < 2:
        raise ValueError(
            f"Need at least 2 arena models to start a battle (found {len(rows)}). "
            f"Register more models first."
        )

    picked = random.sample(list(rows), 2)
    # Randomly assign to position A or B (blind)
    if random.random() < 0.5:
        picked.reverse()
    return dict(picked[0]), dict(picked[1])



async def run_inference(model_name: str, prompt: str) -> dict:
    """
    Run inference on a single model via Ollama streaming API.
    Measures time-to-first-token, total time, token count, and tokens/sec.

    On timeout (120s), returns a placeholder response.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
        },
    }

    response_text = ""
    tokens_generated = 0
    ttft_ms = None
    start_time = time.perf_counter()

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=30.0,
                read=OLLAMA_INFERENCE_TIMEOUT_S,
                write=30.0,
                pool=30.0,
            )
        ) as client:
            async with client.stream("POST", url, json=payload) as stream:
                async for line in stream.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("response", "")
                    if token:
                        if ttft_ms is None:
                            ttft_ms = (time.perf_counter() - start_time) * 1000
                        response_text += token
                        tokens_generated += 1

                    if chunk.get("done", False):
                        # Ollama reports eval_count in the final chunk
                        eval_count = chunk.get("eval_count")
                        if eval_count is not None:
                            tokens_generated = eval_count
                        break

    except httpx.TimeoutException:
        logger.warning("Model %s timed out after %ds", model_name, OLLAMA_INFERENCE_TIMEOUT_S)
        total_ms = (time.perf_counter() - start_time) * 1000
        return {
            "response": f"[Generation timed out after {OLLAMA_INFERENCE_TIMEOUT_S}s]",
            "ttft_ms": ttft_ms,
            "total_ms": total_ms,
            "tokens_generated": tokens_generated,
            "tokens_per_second": 0.0,
            "timed_out": True,
        }
    except httpx.ConnectError as e:
        logger.error("Cannot connect to Ollama for model %s: %s", model_name, e)
        return {
            "response": "[Failed to connect to Ollama]",
            "ttft_ms": None,
            "total_ms": 0.0,
            "tokens_generated": 0,
            "tokens_per_second": 0.0,
            "timed_out": False,
            "error": str(e),
        }

    total_ms = (time.perf_counter() - start_time) * 1000
    total_seconds = total_ms / 1000
    tps = tokens_generated / total_seconds if total_seconds > 0 else 0.0

    return {
        "response": response_text,
        "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
        "total_ms": round(total_ms, 1),
        "tokens_generated": tokens_generated,
        "tokens_per_second": round(tps, 1),
        "timed_out": False,
    }


async def run_battle(prompt: str, model_a: dict, model_b: dict) -> dict:
    """
    Run a sequential battle: Model A generates -> unload -> Model B generates -> unload.

    Returns battle result dict with both responses and latency data.
    """
    model_a_name = model_a["ollama_name"]
    model_b_name = model_b["ollama_name"]

    logger.info("Battle: %s (A) vs %s (B)", model_a_name, model_b_name)

    # --- Model A ---
    logger.info("Generating from Model A: %s", model_a_name)
    result_a = await run_inference(model_a_name, prompt)

    # Unload Model A to free VRAM
    await unload_model(model_a_name)

    # --- Model B ---
    logger.info("Generating from Model B: %s", model_b_name)
    result_b = await run_inference(model_b_name, prompt)

    # Unload Model B
    await unload_model(model_b_name)

    logger.info(
        "Battle complete: A=%d tokens (%.1f ms), B=%d tokens (%.1f ms)",
        result_a["tokens_generated"], result_a["total_ms"],
        result_b["tokens_generated"], result_b["total_ms"],
    )

    return {
        "response_a": result_a["response"],
        "response_b": result_b["response"],
        "model_a_ttft_ms": result_a["ttft_ms"],
        "model_b_ttft_ms": result_b["ttft_ms"],
        "model_a_total_ms": result_a["total_ms"],
        "model_b_total_ms": result_b["total_ms"],
        "model_a_tokens": result_a["tokens_generated"],
        "model_b_tokens": result_b["tokens_generated"],
        "model_a_tps": result_a["tokens_per_second"],
        "model_b_tps": result_b["tokens_per_second"],
    }
