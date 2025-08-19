from fastapi import APIRouter, Query
import uuid

router = APIRouter()


@router.get("/microsites/common/session_id", tags=["Microsites - Common"])
def get_session_id(ip: str = Query(..., description="Client IP address")):
    """
    Generate a deterministic UUID (v5) session id from the provided IP address.
    """
    session_id = uuid.uuid5(uuid.NAMESPACE_DNS, ip)
    return {"ip": ip, "session_id": str(session_id)}
