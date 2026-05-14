from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from redis.asyncio import Redis

from app.api.auth import router as auth_router
from app.api.task import router as task_router
from app.api.users import router as users_router
from app.api.websocket import router as websocket_router
from app.core import redis_client
from app.middleware.request_timing import RequestTimingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.close_redis_pool()


app = FastAPI(lifespan=lifespan)

# app.add_middleware(RequestTimingMiddleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(task_router)
app.include_router(websocket_router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
