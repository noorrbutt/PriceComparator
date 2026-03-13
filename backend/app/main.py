import asyncio
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.db.database import create_tables

# This is the Windows fix — must be at the top before anything else runs
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for FastAPI."""
    # Startup: create database tables
    await create_tables()
    print("[FastAPI] Application startup complete")
    yield
    # Shutdown
    print("[FastAPI] Application shutdown")


app = FastAPI(
    title="Price Comparator API",
    description="Compares prices from Daraz and OLX with caching",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {"status": "running", "message": "Price Comparator API is live"}
