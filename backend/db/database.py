"""
SQLite database via aiosqlite — battles, votes, Elo, training runs.
PRAGMA foreign_keys = ON on every connection.
"""
import aiosqlite
from backend.config import DATABASE_PATH

SCHEMA_SQL = """
-- Training runs
CREATE TABLE IF NOT EXISTS training_runs (
    id TEXT PRIMARY KEY,
    base_model TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    config JSON NOT NULL,
    status TEXT DEFAULT 'pending',
    final_loss REAL,
    total_steps INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    checkpoint_path TEXT,
    gguf_path TEXT,
    ollama_model_name TEXT
);

-- Datasets
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    format_detected TEXT,
    num_samples INTEGER,
    avg_token_length REAL,
    formatted_path TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Models in the arena
CREATE TABLE IF NOT EXISTS arena_models (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ollama_name TEXT NOT NULL,
    source TEXT NOT NULL,
    training_run_id TEXT,
    elo_rating REAL DEFAULT 1200.0,
    total_battles INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_losses INTEGER DEFAULT 0,
    total_ties INTEGER DEFAULT 0,
    avg_ttft_ms REAL,
    avg_tps REAL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (training_run_id) REFERENCES training_runs(id)
);

-- Battle history
CREATE TABLE IF NOT EXISTS battles (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    prompt_category TEXT,
    model_a_id TEXT NOT NULL,
    model_b_id TEXT NOT NULL,
    response_a TEXT,
    response_b TEXT,
    model_a_ttft_ms REAL,
    model_b_ttft_ms REAL,
    model_a_total_ms REAL,
    model_b_total_ms REAL,
    model_a_tokens INTEGER,
    model_b_tokens INTEGER,
    winner TEXT,
    model_a_elo_before REAL,
    model_b_elo_before REAL,
    model_a_elo_after REAL,
    model_b_elo_after REAL,
    voted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_a_id) REFERENCES arena_models(id),
    FOREIGN KEY (model_b_id) REFERENCES arena_models(id)
);

-- Elo history for charting
CREATE TABLE IF NOT EXISTS elo_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    elo_rating REAL NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES arena_models(id)
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_arena_models_elo ON arena_models(elo_rating DESC);
CREATE INDEX IF NOT EXISTS idx_battles_model_a ON battles(model_a_id);
CREATE INDEX IF NOT EXISTS idx_battles_model_b ON battles(model_b_id);
CREATE INDEX IF NOT EXISTS idx_battles_created ON battles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_elo_history_model ON elo_history(model_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_training_runs_status ON training_runs(status);
"""


async def get_db() -> aiosqlite.Connection:
    """Open a connection with foreign keys enforced and row factory set."""
    db = await aiosqlite.connect(str(DATABASE_PATH))
    await db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    """Create all tables and indexes if they don't exist."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    finally:
        await db.close()
