"""Leaderboard — ranked models by Elo with stats, Elo history, aggregates."""
from fastapi import APIRouter, HTTPException, Query

from backend.db.database import get_db

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


# ---------------------------------------------------------------------------
# GET /api/leaderboard — ranked models by Elo with stats
# ---------------------------------------------------------------------------

@router.get("")
async def get_leaderboard():
    """Return all arena models ranked by Elo rating with win-rate percentage."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM arena_models ORDER BY elo_rating DESC"
        )
        rows = await cursor.fetchall()

        models = []
        for rank, row in enumerate(rows, 1):
            total = row["total_battles"]
            win_rate = round(row["total_wins"] / total * 100, 1) if total > 0 else 0.0
            models.append({
                "rank": rank,
                "id": row["id"],
                "name": row["name"],
                "ollama_name": row["ollama_name"],
                "source": row["source"],
                "elo_rating": row["elo_rating"],
                "total_battles": total,
                "total_wins": row["total_wins"],
                "total_losses": row["total_losses"],
                "total_ties": row["total_ties"],
                "win_rate": win_rate,
                "avg_ttft_ms": row["avg_ttft_ms"],
                "avg_tps": row["avg_tps"],
                "registered_at": row["registered_at"],
            })

        return {"models": models}
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# GET /api/leaderboard/{model_id}/history — Elo history over time
# ---------------------------------------------------------------------------

@router.get("/{model_id}/history")
async def get_elo_history(model_id: str, limit: int = Query(100, ge=1, le=1000)):
    """Return Elo rating history for a model, ordered chronologically."""
    db = await get_db()
    try:
        # Verify model exists
        cursor = await db.execute(
            "SELECT id, name, elo_rating FROM arena_models WHERE id = ?",
            (model_id,),
        )
        model = await cursor.fetchone()
        if not model:
            raise HTTPException(404, f"Arena model '{model_id}' not found.")

        cursor = await db.execute(
            """SELECT elo_rating, recorded_at
               FROM elo_history
               WHERE model_id = ?
               ORDER BY recorded_at ASC
               LIMIT ?""",
            (model_id, limit),
        )
        rows = await cursor.fetchall()

        return {
            "model_id": model_id,
            "model_name": model["name"],
            "current_elo": model["elo_rating"],
            "history": [
                {"elo_rating": row["elo_rating"], "recorded_at": row["recorded_at"]}
                for row in rows
            ],
        }
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# GET /api/leaderboard/stats — aggregate stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_leaderboard_stats():
    """Aggregate arena stats: total battles, vote distribution, model count."""
    db = await get_db()
    try:
        # Total battles (voted only)
        cursor = await db.execute(
            "SELECT COUNT(*) AS cnt FROM battles WHERE voted_at IS NOT NULL"
        )
        total_battles = (await cursor.fetchone())["cnt"]

        # Vote distribution
        cursor = await db.execute(
            """SELECT
                 SUM(CASE WHEN winner = 'a' THEN 1 ELSE 0 END) AS wins_a,
                 SUM(CASE WHEN winner = 'b' THEN 1 ELSE 0 END) AS wins_b,
                 SUM(CASE WHEN winner = 'tie' THEN 1 ELSE 0 END) AS ties,
                 SUM(CASE WHEN winner IS NULL AND voted_at IS NOT NULL THEN 1 ELSE 0 END) AS skips
               FROM battles
               WHERE voted_at IS NOT NULL"""
        )
        dist = await cursor.fetchone()

        # Pending (unvoted) battles
        cursor = await db.execute(
            "SELECT COUNT(*) AS cnt FROM battles WHERE voted_at IS NULL"
        )
        pending = (await cursor.fetchone())["cnt"]

        # Model count
        cursor = await db.execute("SELECT COUNT(*) AS cnt FROM arena_models")
        model_count = (await cursor.fetchone())["cnt"]

        return {
            "total_battles": total_battles,
            "pending_battles": pending,
            "model_count": model_count,
            "vote_distribution": {
                "a_wins": dist["wins_a"] or 0,
                "b_wins": dist["wins_b"] or 0,
                "ties": dist["ties"] or 0,
                "skips": dist["skips"] or 0,
            },
        }
    finally:
        await db.close()
