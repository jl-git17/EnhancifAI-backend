from fastapi import APIRouter, Depends, Request
import uuid

from enhancifai_backend.server.utils import verify_secret_key

router = APIRouter()


@router.get("/microsites/common/session_id", tags=["Microsites - Common"])
async def get_session_id(request: Request, _: str = Depends(verify_secret_key)):
    """
    Generate a deterministic UUID (v5) session id from the client's IP address.

    IP extraction priority:
    - X-Forwarded-For header (first value) — for proxies/load balancers
    - request.client.host fallback
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # X-Forwarded-For may contain multiple comma-separated IPs; take the first one
        ip = xff.split(",")[0].strip()
    else:
        client = request.client
        ip = client.host if client else None

    if not ip:
        return {"error": "Could not determine client IP"}

    session_id = uuid.uuid5(uuid.NAMESPACE_DNS, ip)
    return {"session_id": str(session_id)}
