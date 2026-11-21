from contextlib import asynccontextmanager
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.redis_client import redis_store
from app.routers.auth import router as auth_router
from app.routers.photos import router as photos_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("auth.main")

STATIC_DIR = Path(__file__).parent / "app" / "static"
UPLOAD_DIR = Path(__file__).parent / settings.UPLOAD_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and redis connection
    logger.info("Initializing database tables...")
    init_db()
    logger.info("Database initialized.")

    logger.info("Connecting to Redis...")
    redis_store.connect()
    if redis_store.is_fallback:
        logger.info("Redis: Using in-memory fallback (fakeredis). Fully functional for local testing!")
    else:
        logger.info("Redis: Successfully connected to Redis server.")

    yield

    # Shutdown
    logger.info("Shutting down and releasing resources...")
    redis_store.close()
    logger.info("Clean shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    description="FastAPI Authentication & PicShare Photo Gallery with Cookie-based JWT Auth",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend applications (allowing credentials for cookies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Authentication & Photos Routers
app.include_router(auth_router)
app.include_router(photos_router)

# Mount static files directory
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount uploaded files directory (for originals and thumbnails)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/", include_in_schema=False)
def serve_frontend():
    """Serves the simple single-page frontend application."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        content={"message": "Frontend index.html not found. Check /docs for API documentation."}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
