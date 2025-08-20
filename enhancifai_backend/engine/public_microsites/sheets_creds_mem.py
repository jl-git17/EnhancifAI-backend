
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SheetsCredsMemory:
    """A class to manage Google Sheets credentials in memory, grouped by session ID.

    This class intentionally does not configure logging handlers; calling code or
    the application should configure the logging level and handlers as needed.
    """

    def __init__(self) -> None:
        self.creds: dict[str, Any] = {}
        self.states: dict[str, str] = {}
        logger.debug("SheetsCredsMemory initialized")

    # CREDS

    def set_creds(self, session_id: str, credentials: Any) -> None:
        """Set the credentials for a given session ID.

        Logs the operation and stores the credentials in memory.
        """
        logger.debug("set_creds: session_id=%s - storing credentials", session_id)
        self.creds[session_id] = credentials

    def get_creds(self, session_id: str) -> Optional[Any]:
        """Get the credentials for a given session ID.

        Returns None when no credentials are stored for the session.
        """
        exists = session_id in self.creds
        logger.debug("get_creds: session_id=%s - exists=%s", session_id, exists)
        creds = self.creds.get(session_id)
        if creds is None:
            logger.info("get_creds: no credentials found for session_id=%s", session_id)
        return creds

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
        """Check if credentials exist for a given session ID."""
        result = session_id in self.creds
        logger.debug("has_creds: session_id=%s -> %s", session_id, result)
        return result

    # STATES

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
