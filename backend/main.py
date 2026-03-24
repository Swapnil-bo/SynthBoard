"""FastAPI app entry, CORS, lifespan."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.database import init_db
from backend.routers import datasets, models, system, training
from backend.utils.capabilities import run_startup_probe

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, run capability probe. Shutdown: nothing for now."""
    await init_db()
    probe = run_startup_probe()
    if probe.warnings:
        for w in probe.warnings:
            logger.warning("Capability warning: %s", w)
    yield


app = FastAPI(
    title="SynthBoard",
    description="Local fine-tuning pipeline + model arena",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Vite dev server on any port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(datasets.router)
app.include_router(training.router)
app.include_router(models.router)
