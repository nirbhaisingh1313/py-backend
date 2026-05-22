from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from redis.asyncio import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.task import router as task_router
from app.api.users import router as users_router
from app.api.websocket import router as websocket_router
from app.core import redis_client
from app.core.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from app.core.logging_setup import configure_logging
from app.middleware.structured_logging import StructuredLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield
    await redis_client.close_redis_pool()


app = FastAPI(lifespan=lifespan)

app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.add_middleware(StructuredLoggingMiddleware)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(task_router)
app.include_router(websocket_router)
