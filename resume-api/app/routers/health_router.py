import time
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.cache.redis_client import redis_client
from app.messaging.rabbitmq_client import publisher
from app.core.metrics import metrics

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/live")
def liveness():
    return {
        "status":    "alive",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "not ready", "database": str(e)}
        )

    return {
        "status":    "ready",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("")
def full_health(db: Session = Depends(get_db)):
    """Full health check — all dependencies."""

    db_status = "ok"
    try:
        db.execute("SELECT 1")
    except Exception as e:
        db_status = f"error: {e}"

    redis_status = "ok"
    try:
        redis_client.ping()
    except Exception as e:
        redis_status = f"error: {e}"

    mq_status = (
        "ok"
        if publisher.channel and not publisher.connection.is_closed
        else "error: not connected"
    )

    all_ok  = all(s == "ok" for s in [db_status, redis_status, mq_status])
    uptime  = int(time.time() - metrics.start_time)
    hours   = uptime // 3600
    minutes = (uptime % 3600) // 60
    seconds = uptime % 60

    return {
        "status":       "healthy" if all_ok else "degraded",
        "version":      "1.0",
        "uptime":       f"{hours}h {minutes}m {seconds}s",
        "timestamp":    datetime.utcnow().isoformat(),
        "dependencies": {
            "database": db_status,
            "redis":    redis_status,
            "rabbitmq": mq_status
        }
    }