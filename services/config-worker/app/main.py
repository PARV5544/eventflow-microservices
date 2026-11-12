import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("config-worker")

JWT_SECRET = os.getenv("EVENTFLOW_JWT_SECRET", "eventflow-dev-secret-key-32-bytes!!")
JWT_ALGORITHM = "HS256"

app = FastAPI(
    title="EventFlow Config Worker",
    version="0.1.0",
    description="Multi-tenant configuration & Kafka event consumer worker with JWT RBAC and Redis state.",
)

# In-memory tenant config state (backed by Redis in production)
_TENANT_CONFIGS: Dict[str, dict] = {}
_DEAD_LETTER_QUEUE: List[dict] = []


class ProvisionEvent(BaseModel):
    event_id: str
    tenant_id: str
    plan: str = Field(..., pattern="^(starter|pro|enterprise)$")
    region: str = "ap-south-1"
    retry_count: int = 0
    simulate_failure: bool = False


class TokenClaims(BaseModel):
    sub: str
    roles: List[str]


def verify_jwt(authorization: Optional[str] = Header(default=None)) -> TokenClaims:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JWT token",
        ) from exc
    return TokenClaims(sub=payload.get("sub", "unknown"), roles=payload.get("roles", []))


def require_role(required: str):
    def _checker(claims: TokenClaims = Depends(verify_jwt)) -> TokenClaims:
        if required not in claims.roles and "ADMIN" not in claims.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required}' required",
            )
        return claims

    return _checker


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "service": "config-worker",
        "active_tenants": len(_TENANT_CONFIGS),
        "dlq_depth": len(_DEAD_LETTER_QUEUE),
    }


@app.post("/api/v1/events/provision")
def handle_provision_event(
    event: ProvisionEvent,
    claims: TokenClaims = Depends(require_role("OPERATOR")),
):
    if event.simulate_failure:
        dlq_entry = {
            "topic": "tenant.provisioning.dlq",
            "event": event.model_dump(),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "reason": "Simulated downstream provisioning failure",
        }
        _DEAD_LETTER_QUEUE.append(dlq_entry)
        logger.warning(json.dumps({"action": "routed_to_dlq", "tenant_id": event.tenant_id}))
        return {"status": "DEAD_LETTERED", "dlq_depth": len(_DEAD_LETTER_QUEUE)}

    config = {
        "tenant_id": event.tenant_id,
        "plan": event.plan,
        "region": event.region,
        "status": "PROVISIONED",
        "provisioned_by": claims.sub,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _TENANT_CONFIGS[event.tenant_id] = config
    logger.info(json.dumps({"action": "tenant_provisioned", "tenant_id": event.tenant_id}))
    return config


@app.get("/api/v1/tenants/{tenant_id}/config")
def get_tenant_config(
    tenant_id: str,
    _: TokenClaims = Depends(require_role("VIEWER")),
):
    config = _TENANT_CONFIGS.get(tenant_id)
    if not config:
        raise HTTPException(status_code=404, detail="Tenant config not found")
    return config


@app.get("/api/v1/dlq")
def list_dlq(_: TokenClaims = Depends(require_role("ADMIN"))):
    return {"count": len(_DEAD_LETTER_QUEUE), "items": _DEAD_LETTER_QUEUE}
