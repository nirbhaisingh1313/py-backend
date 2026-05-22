from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.schemas.health import LivenessResponse, ReadinessResponse
from app.services import health_service

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description=(
        "Reports whether the API process is running. Does not check external "
        "dependencies. Use for restart decisions (e.g. Kubernetes livenessProbe)."
    ),
)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Reports whether the API can serve traffic: database, Redis, and at least "
        "one Celery worker must be reachable. Returns 503 when not ready. Use for "
        "load-balancer / Kubernetes readinessProbe."
    ),
)
async def readiness() -> JSONResponse:
    report = await health_service.run_readiness_checks()
    body = ReadinessResponse(
        status="ready" if report.is_ready else "not_ready",
        checks=report.checks,
    )
    status_code = (
        status.HTTP_200_OK if report.is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())
