import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import create_tables
from app.limiter import limiter
from app.routers import analytics, auth, businesses, chat, conversations, me

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — creating tables if needed")
    await create_tables()
    logger.info("Database ready")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="پلتفرم پشتیبانی مشتریان مبتنی بر هوش مصنوعی",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(me.router)
app.include_router(chat.router)
app.include_router(businesses.router)
app.include_router(conversations.router)
app.include_router(analytics.router)


@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "app": settings.app_name}


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
