from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import engine, Base
from app.db_migrate import run_migrations
from app.routers import admin, auth, dashboard, leaderboard, matches, predictions, simulation, tournament
from app.seed import seed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_migrations(engine)
    await seed()
    logger.info("Application startup complete")
    yield


app = FastAPI(title="World Cup Prediction Game", version="1.0.0", lifespan=lifespan)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("DB integrity error on %s %s: %s", request.method, request.url.path, exc.orig)
    return JSONResponse(status_code=400, content={"detail": "A record with this value already exists"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(matches.router)
app.include_router(predictions.router)
app.include_router(leaderboard.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(tournament.router)

app.include_router(simulation.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
