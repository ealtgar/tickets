import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import crud
from .database import Base, SessionLocal, engine
from .routers import auth, comments, oauth, tickets, users

STATIC_DIR = Path(__file__).parent / "static"

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        removed = crud.purge_expired_refresh_tokens(db)
    if removed:
        print(f"[auth] {removed} refresh tokens expirados eliminados")
    yield


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Tickets API",
    description="Backend sencillo de un sistema de tickets.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(users.router)


@app.get("/health", tags=["root"])
def health():
    return {"status": "healthy"}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
