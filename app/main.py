from fastapi import Depends,FastAPI
from redis.asyncio import Redis

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.task import router as task_router

from app.core import redis_client
app = FastAPI()

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(task_router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/redis-test")
async def redis_test(redis: Redis = Depends(redis_client.get_redis)):
    await redis.set("name", "nirbhai")

    value = await redis.get("name")

    return {"value": value}