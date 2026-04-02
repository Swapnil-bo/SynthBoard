"""Battle generation, vote submission, Elo calculation."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from backend.db.database import get_db
from backend.models.arena import (
    BattleDetailResponse,
    BattleHistoryResponse,
    BattleRequest,
    BattleResponse,
    VoteRequest,
    VoteResponse,
)
from backend.services.arena_engine import (
    get_random_prompt,
    run_battle,
    select_battle_models,
)
from backend.services.elo_calculator import calculate_elo
from backend.services.model_manager import check_ollama_running

router = APIRouter(prefix="/api/arena", tags=["arena"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# POST /api/arena/battle — generate a new battle
# ---------------------------------------------------------------------------

@router.post("/battle", response_model=BattleResponse)
async def create_battle(request: BattleRequest = None):
    """
    Generate a new arena battle.

    Pre-flight: check Ollama is running and at least 2 models registered.
    Randomly picks 2 models, assigns to positions A/B (blind),
    runs sequential inference, saves to DB, returns blinded responses.
    """
    if request is None:
        request = BattleRequest()

    # Pre-flight: Ollama running?
    if not await check_ollama_running():
        raise HTTPException(
            503,
            "Ollama is not running. Start Ollama before using the arena.",
        )

    # Pre-flight: at least 2 models?
    try:
        model_a, model_b = await select_battle_models()
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Get prompt
    prompt_category = None
    if request.prompt:
        prompt = request.prompt
    else:
        try:
            prompt, prompt_category = get_random_prompt()
        except ValueError as e:
            raise HTTPException(500, str(e))

    # Run sequential inference
    battle_result = await run_battle(prompt, model_a, model_b)

    # Save to DB
    battle_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO battles
               (id, prompt, prompt_category,
                model_a_id, model_b_id,
                response_a, response_b,
                model_a_ttft_ms, model_b_ttft_ms,
                model_a_total_ms, model_b_total_ms,
                model_a_tokens, model_b_tokens,
                model_a_elo_before, model_b_elo_before,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                battle_id, prompt, prompt_category,
                model_a["id"], model_b["id"],
                battle_result["response_a"], battle_result["response_b"],
                battle_result["model_a_ttft_ms"], battle_result["model_b_ttft_ms"],
                battle_result["model_a_total_ms"], battle_result["model_b_total_ms"],
                battle_result["model_a_tokens"], battle_result["model_b_tokens"],
                model_a["elo_rating"], model_b["elo_rating"],
                now,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    logger.info(
        "Battle %s created: %s vs %s",
        battle_id, model_a["name"], model_b["name"],
    )

    return BattleResponse(
        id=battle_id,
        prompt=prompt,
        prompt_category=prompt_category,
        response_a=battle_result["response_a"],
        response_b=battle_result["response_b"],
        model_a_ttft_ms=battle_result["model_a_ttft_ms"],
        model_b_ttft_ms=battle_result["model_b_ttft_ms"],
        model_a_total_ms=battle_result["model_a_total_ms"],
        model_b_total_ms=battle_result["model_b_total_ms"],
        model_a_tokens=battle_result["model_a_tokens"],
        model_b_tokens=battle_result["model_b_tokens"],
    )


# ---------------------------------------------------------------------------
# POST /api/arena/battle/{id}/vote — submit vote
# ---------------------------------------------------------------------------

@router.post("/battle/{battle_id}/vote", response_model=VoteResponse)
async def submit_vote(battle_id: str, request: VoteRequest):
    """
    Submit a vote on a battle.

    winner='a'|'b'|'tie' updates Elo ratings.
    winner='skip' records the battle with winner=NULL, no Elo change.
    """
    db = await get_db()
    try:
        # Fetch battle
        cursor = await db.execute(
            "SELECT * FROM battles WHERE id = ?", (battle_id,)
        )
        battle = await cursor.fetchone()
        if not battle:
            raise HTTPException(404, f"Battle '{battle_id}' not found.")
        if battle["voted_at"] is not None:
            raise HTTPException(409, f"Battle '{battle_id}' has already been voted on.")

        model_a_id = battle["model_a_id"]
        model_b_id = battle["model_b_id"]

        # Fetch model records
        cursor = await db.execute(
            "SELECT * FROM arena_models WHERE id = ?", (model_a_id,)
        )
        model_a = await cursor.fetchone()
        cursor = await db.execute(
            "SELECT * FROM arena_models WHERE id = ?", (model_b_id,)
        )
        model_b = await cursor.fetchone()

        if not model_a or not model_b:
            raise HTTPException(
                500,
                "One or both arena models no longer exist. Cannot process vote.",
            )

        now = datetime.now(timezone.utc).isoformat()
        winner = request.winner
        elo_a_before = model_a["elo_rating"]
        elo_b_before = model_b["elo_rating"]

        if winner == "skip":
            # Skip: record battle but no Elo change
            elo_a_after = elo_a_before
            elo_b_after = elo_b_before
            db_winner = None
        else:
            # Calculate new Elo
            elo_a_after, elo_b_after = calculate_elo(
                elo_a_before, elo_b_before, winner
            )
            db_winner = winner

        # Update battle record
        await db.execute(
            """UPDATE battles
               SET winner = ?, voted_at = ?,
                   model_a_elo_before = ?, model_b_elo_before = ?,
                   model_a_elo_after = ?, model_b_elo_after = ?
               WHERE id = ?""",
            (db_winner, now, elo_a_before, elo_b_before,
             elo_a_after, elo_b_after, battle_id),
        )

        if winner != "skip":
            # Update arena_models Elo and battle stats
            # Model A
            wins_a = 1 if winner == "a" else 0
            losses_a = 1 if winner == "b" else 0
            ties_a = 1 if winner == "tie" else 0
            await db.execute(
                """UPDATE arena_models
                   SET elo_rating = ?,
                       total_battles = total_battles + 1,
                       total_wins = total_wins + ?,
                       total_losses = total_losses + ?,
                       total_ties = total_ties + ?
                   WHERE id = ?""",
                (elo_a_after, wins_a, losses_a, ties_a, model_a_id),
            )

            # Model B
            wins_b = 1 if winner == "b" else 0
            losses_b = 1 if winner == "a" else 0
            ties_b = 1 if winner == "tie" else 0
            await db.execute(
                """UPDATE arena_models
                   SET elo_rating = ?,
                       total_battles = total_battles + 1,
                       total_wins = total_wins + ?,
                       total_losses = total_losses + ?,
                       total_ties = total_ties + ?
                   WHERE id = ?""",
                (elo_b_after, wins_b, losses_b, ties_b, model_b_id),
            )

            # Record Elo history
            await db.execute(
                "INSERT INTO elo_history (model_id, elo_rating, recorded_at) VALUES (?, ?, ?)",
                (model_a_id, elo_a_after, now),
            )
            await db.execute(
                "INSERT INTO elo_history (model_id, elo_rating, recorded_at) VALUES (?, ?, ?)",
                (model_b_id, elo_b_after, now),
            )

        # Update avg latency stats for both models
        await _update_model_latency_stats(db, model_a_id)
        await _update_model_latency_stats(db, model_b_id)

        await db.commit()

        logger.info(
            "Vote on battle %s: winner=%s, A(%s) %.1f->%.1f, B(%s) %.1f->%.1f",
            battle_id, winner,
            model_a["name"], elo_a_before, elo_a_after,
            model_b["name"], elo_b_before, elo_b_after,
        )

        return VoteResponse(
            battle_id=battle_id,
            winner=winner,
            model_a_name=model_a["name"],
            model_b_name=model_b["name"],
            model_a_id=model_a_id,
            model_b_id=model_b_id,
            model_a_elo_before=elo_a_before,
            model_b_elo_before=elo_b_before,
            model_a_elo_after=elo_a_after,
            model_b_elo_after=elo_b_after,
        )
    finally:
        await db.close()


async def _update_model_latency_stats(db, model_id: str) -> None:
    """Recompute avg TTFT and avg TPS for a model from all its battles."""
    cursor = await db.execute(
        """SELECT
             AVG(CASE WHEN model_a_id = ? THEN model_a_ttft_ms
                       WHEN model_b_id = ? THEN model_b_ttft_ms END) AS avg_ttft,
             AVG(CASE WHEN model_a_id = ? THEN
                           CASE WHEN model_a_total_ms > 0 AND model_a_tokens > 0
                                THEN model_a_tokens * 1000.0 / model_a_total_ms END
                       WHEN model_b_id = ? THEN
                           CASE WHEN model_b_total_ms > 0 AND model_b_tokens > 0
                                THEN model_b_tokens * 1000.0 / model_b_total_ms END
                  END) AS avg_tps
           FROM battles
           WHERE (model_a_id = ? OR model_b_id = ?) AND voted_at IS NOT NULL""",
        (model_id, model_id, model_id, model_id, model_id, model_id),
    )
    row = await cursor.fetchone()
    if row:
        await db.execute(
            "UPDATE arena_models SET avg_ttft_ms = ?, avg_tps = ? WHERE id = ?",
            (
                round(row["avg_ttft"], 1) if row["avg_ttft"] else None,
                round(row["avg_tps"], 1) if row["avg_tps"] else None,
                model_id,
            ),
        )


# ---------------------------------------------------------------------------
# GET /api/arena/battle/{id} — battle details (reveals models after vote)
# ---------------------------------------------------------------------------

@router.get("/battle/{battle_id}", response_model=BattleDetailResponse)
async def get_battle(battle_id: str):
    """
    Get battle details. Model identities are revealed only after voting.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM battles WHERE id = ?", (battle_id,)
        )
        battle = await cursor.fetchone()
        if not battle:
            raise HTTPException(404, f"Battle '{battle_id}' not found.")

        voted = battle["voted_at"] is not None

        # Only reveal model names if voted
        model_a_name = None
        model_b_name = None
        if voted:
            cursor = await db.execute(
                "SELECT name FROM arena_models WHERE id = ?",
                (battle["model_a_id"],),
            )
            row_a = await cursor.fetchone()
            cursor = await db.execute(
                "SELECT name FROM arena_models WHERE id = ?",
                (battle["model_b_id"],),
            )
            row_b = await cursor.fetchone()
            model_a_name = row_a["name"] if row_a else "[deleted]"
            model_b_name = row_b["name"] if row_b else "[deleted]"

        return BattleDetailResponse(
            id=battle["id"],
            prompt=battle["prompt"],
            prompt_category=battle["prompt_category"],
            response_a=battle["response_a"],
            response_b=battle["response_b"],
            model_a_ttft_ms=battle["model_a_ttft_ms"],
            model_b_ttft_ms=battle["model_b_ttft_ms"],
            model_a_total_ms=battle["model_a_total_ms"],
            model_b_total_ms=battle["model_b_total_ms"],
            model_a_tokens=battle["model_a_tokens"],
            model_b_tokens=battle["model_b_tokens"],
            winner=battle["winner"],
            model_a_name=model_a_name,
            model_b_name=model_b_name,
            model_a_id=battle["model_a_id"] if voted else None,
            model_b_id=battle["model_b_id"] if voted else None,
            model_a_elo_before=battle["model_a_elo_before"] if voted else None,
            model_b_elo_before=battle["model_b_elo_before"] if voted else None,
            model_a_elo_after=battle["model_a_elo_after"] if voted else None,
            model_b_elo_after=battle["model_b_elo_after"] if voted else None,
            voted_at=battle["voted_at"],
            created_at=battle["created_at"],
        )
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# GET /api/arena/history — paginated battle history
# ---------------------------------------------------------------------------

@router.get("/history", response_model=BattleHistoryResponse)
async def get_battle_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Paginated battle history, most recent first."""
    offset = (page - 1) * page_size

    db = await get_db()
    try:
        # Total count
        cursor = await db.execute("SELECT COUNT(*) AS cnt FROM battles")
        total = (await cursor.fetchone())["cnt"]

        # Fetch page
        cursor = await db.execute(
            """SELECT b.*,
                      ma.name AS model_a_name_resolved,
                      mb.name AS model_b_name_resolved
               FROM battles b
               LEFT JOIN arena_models ma ON ma.id = b.model_a_id
               LEFT JOIN arena_models mb ON mb.id = b.model_b_id
               ORDER BY b.created_at DESC
               LIMIT ? OFFSET ?""",
            (page_size, offset),
        )
        rows = await cursor.fetchall()

        battles = []
        for row in rows:
            voted = row["voted_at"] is not None
            battles.append(BattleDetailResponse(
                id=row["id"],
                prompt=row["prompt"],
                prompt_category=row["prompt_category"],
                response_a=row["response_a"],
                response_b=row["response_b"],
                model_a_ttft_ms=row["model_a_ttft_ms"],
                model_b_ttft_ms=row["model_b_ttft_ms"],
                model_a_total_ms=row["model_a_total_ms"],
                model_b_total_ms=row["model_b_total_ms"],
                model_a_tokens=row["model_a_tokens"],
                model_b_tokens=row["model_b_tokens"],
                winner=row["winner"],
                model_a_name=row["model_a_name_resolved"] if voted else None,
                model_b_name=row["model_b_name_resolved"] if voted else None,
                model_a_id=row["model_a_id"] if voted else None,
                model_b_id=row["model_b_id"] if voted else None,
                model_a_elo_before=row["model_a_elo_before"] if voted else None,
                model_b_elo_before=row["model_b_elo_before"] if voted else None,
                model_a_elo_after=row["model_a_elo_after"] if voted else None,
                model_b_elo_after=row["model_b_elo_after"] if voted else None,
                voted_at=row["voted_at"],
                created_at=row["created_at"],
            ))

        return BattleHistoryResponse(
            battles=battles,
            total=total,
            page=page,
            page_size=page_size,
        )
    finally:
        await db.close()
