import uuid
import threading
import time
from typing import Any, Dict, Optional
from http.client import HTTPException
from fastapi import APIRouter, Depends, Request

from enhancifai_backend.server.utils import verify_secret_key

router = APIRouter()


class SessionManager:
    """Thread-safe in-memory session manager.

    Sessions are keyed by deterministic UUID v5 values (generated from client IPs).
    Each session stores arbitrary data, creation time and last access time.

    The manager runs a background cleanup thread which evicts sessions that
    have not been accessed within `ttl_seconds`.
    """

    def __init__(self, ttl_seconds: int = 3600, cleanup_interval_seconds: int = 600):
        self.ttl = float(ttl_seconds)
        self.cleanup_interval = float(cleanup_interval_seconds)
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def generate_session_id(self, ip: str) -> str:
        """Return deterministic UUID v5 (as string) for the given IP."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, ip))

    def get_or_create_session_from_ip(self, ip: str) -> str:
        """Return existing session id for IP or create a new session entry."""
        sid = self.generate_session_id(ip)
        now = time.time()
        with self._lock:
            if sid not in self._sessions:
                self._sessions[sid] = {"data": {}, "created": now, "last_access": now}
            else:
                self._sessions[sid]["last_access"] = now
        return sid

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return session dict or None if missing/expired."""
        now = time.time()
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                return None
            # check TTL
            if now - s["last_access"] > self.ttl:
                # expired
                del self._sessions[session_id]
                return None
            # refresh last access
            s["last_access"] = now
            return s

    def set_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Set session data. Returns False if session doesn't exist."""
        with self._lock:
            s = self._sessions.get(session_id)
            if not s:
                return False
            s["data"] = data
            s["last_access"] = time.time()
            return True

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _cleanup_loop(self) -> None:
        while not self._stop_event.wait(self.cleanup_interval):
            now = time.time()
            with self._lock:
                expired = [sid for sid, s in self._sessions.items() if now - s["last_access"] > self.ttl]
                for sid in expired:
                    del self._sessions[sid]

    def stop_cleanup(self) -> None:
        """Stop the background cleanup thread. Call at shutdown if desired."""
        self._stop_event.set()
        if self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1.0)


# module-level manager instance (can be imported and reused elsewhere)
session_manager = SessionManager()

def verify_session_id(session_id: str) -> str:
    """Verify and return the session ID, or raise an HTTPException if invalid."""
    if not session_id or not isinstance(session_id, str):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session_data = session_manager.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    return True


@router.get("/microsites/common/session_id", tags=["Microsites - Common"])
async def get_session_id(request: Request, _: str = Depends(verify_secret_key)):
    """
    Generate a deterministic UUID (v5) session id from the client's IP address and
    register/refresh a session in the in-memory SessionManager.

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

    session_id = session_manager.get_or_create_session_from_ip(ip)
    return {"session_id": session_id}
