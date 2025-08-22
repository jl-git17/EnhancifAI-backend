
import logging
import time
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class SheetsCredsMemory:
    """A class to manage Google Sheets credentials in memory, grouped by session ID.

    Credentials are stored with an expiration timestamp and are kept no longer
    than the configured TTL (default 5 minutes). Expired credentials are removed
    on access and during set operations to avoid stale entries.

    This class intentionally does not configure logging handlers; calling code or
    the application should configure the logging level and handlers as needed.
    """

    # TTL in seconds (5 minutes)
    DEFAULT_TTL = 5 * 60

    def __init__(self, ttl_seconds: int | None = None) -> None:
        # creds maps session_id -> (credentials, expires_at_timestamp)
        self.creds: dict[str, Tuple[Any, float]] = {}
        self.states: dict[str, str] = {}
        self.ttl = ttl_seconds if ttl_seconds is not None else self.DEFAULT_TTL
        logger.debug("SheetsCredsMemory initialized with ttl=%s seconds", self.ttl)

    # Internal helpers

    def _now(self) -> float:
        return time.time()

    def _is_expired(self, expires_at: float) -> bool:
        return self._now() >= expires_at

    def _purge_expired(self) -> None:
        """Remove any expired credential entries."""
        now = self._now()
        expired = [sid for sid, (_c, exp) in self.creds.items() if exp <= now]
        for sid in expired:
            logger.debug("_purge_expired: removing expired creds for session_id=%s", sid)
            del self.creds[sid]

    # CREDS

    def set_creds(self, session_id: str, credentials: Any) -> None:
        """Set the credentials for a given session ID with expiry (TTL).

        Logs the operation and stores the credentials in memory with an expiry
        timestamp equal to now + ttl.
        """
        # Purge expired entries opportunistically to limit memory growth
        self._purge_expired()
        expires_at = self._now() + self.ttl
        logger.debug(
            "set_creds: session_id=%s - storing credentials (expires_at=%s)",
            session_id,
            expires_at,
        )
        self.creds[session_id] = (credentials, expires_at)

    def get_creds(self, session_id: str) -> Optional[Any]:
        """Get the credentials for a given session ID.

        Returns None when no credentials are stored or when they have expired.
        Expired credentials are removed and an info log is emitted.
        """
        entry = self.creds.get(session_id)
        logger.debug("get_creds: session_id=%s - found_entry=%s", session_id, entry is not None)
        if entry is None:
            logger.info("get_creds: no credentials found for session_id=%s", session_id)
            return None

        credentials, expires_at = entry
        if self._is_expired(expires_at):
            logger.info("get_creds: credentials expired for session_id=%s; removing", session_id)
            # remove expired entry
            try:
                del self.creds[session_id]
            except KeyError:
                pass
            return None

        return credentials

    def clear_creds(self, session_id: str) -> None:
        """Clear the credentials for a given session ID.

        If no credentials are present for the session, this is a no-op but logged.
        """
        if session_id in self.creds:
            logger.debug("clear_creds: session_id=%s - removing credentials", session_id)
            del self.creds[session_id]
        else:
            logger.debug("clear_creds: session_id=%s - no credentials to remove", session_id)

    def has_creds(self, session_id: str) -> bool:
        """Check if credentials exist and are not expired for a given session ID."""
        entry = self.creds.get(session_id)
        if entry is None:
            logger.debug("has_creds: session_id=%s -> False (no entry)", session_id)
            return False
        _, expires_at = entry
        if self._is_expired(expires_at):
            logger.debug("has_creds: session_id=%s -> False (expired)", session_id)
            # remove expired entry
            try:
                del self.creds[session_id]
            except KeyError:
                pass
            return False
        logger.debug("has_creds: session_id=%s -> True", session_id)
        return True

    # STATES (unchanged)

    def set_state(self, session_id: str, state: str) -> None:
        """Set the state for a given session ID."""
        logger.debug("set_state: session_id=%s state=%s", session_id, state)
        self.states[session_id] = state

    def get_state_by_session_id(self, session_id: str) -> Optional[str]:
        """Get the state for a given session ID."""
        exists = session_id in self.states
        logger.debug("get_state_by_session_id: session_id=%s - exists=%s", session_id, exists)
        state = self.states.get(session_id)
        if state is None:
            logger.info("get_state_by_session_id: no state found for session_id=%s", session_id)
        return state

    def get_session_id_of_state(self, state: str) -> Optional[str]:
        """Get the session ID for a given state.

        Performs a linear search and logs the search progress. Returns the first
        matching session_id or None when not found.
        """
        logger.debug("get_session_id_of_state: searching for state=%s", state)
        for session_id, s in self.states.items():
            logger.debug("get_session_id_of_state: checking session_id=%s (state=%s)", session_id, s)
            if s == state:
                logger.debug("get_session_id_of_state: found session_id=%s for state=%s", session_id, state)
                return session_id
        logger.info("get_session_id_of_state: no session found for state=%s", state)
        return None

    def clear_state(self, session_id: str) -> None:
        """Clear the state for a given session ID."""
        if session_id in self.states:
            logger.debug("clear_state: session_id=%s - removing state", session_id)
            del self.states[session_id]
        else:
            logger.debug("clear_state: session_id=%s - no state to remove", session_id)


sheets_creds_memory = SheetsCredsMemory()
