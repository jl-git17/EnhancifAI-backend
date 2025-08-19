
class SheetsCredsMemory:
    """
    A class to manage Google Sheets credentials in memory.
    Grouped by provided session ID.
    """
    def __init__(self):
        self.creds = {}
        self.states = {}

    # CREDS

    def set_creds(self, session_id: str, credentials):
        """
        Set the credentials for a given session ID.
        """
        self.creds[session_id] = credentials

    def get_creds(self, session_id: str):
        """
        Get the credentials for a given session ID.
        """
        return self.creds.get(session_id)

    def clear_creds(self, session_id: str):
        """
        Clear the credentials for a given session ID.
        """
        if session_id in self.creds:
            del self.creds[session_id]
    def has_creds(self, session_id: str):
        """
        Check if credentials exist for a given session ID.
        """
        return session_id in self.creds
    
    # STATES
    
    def set_state(self, session_id: str, state: str):
        """
        Set the state for a given session ID.
        """
        self.states[session_id] = state

    def get_state_by_session_id(self, session_id: str):
        """
        Get the state for a given session ID.
        """
        return self.states.get(session_id)

    def get_session_id_of_state(self, state: str):
        """
        Get the session ID for a given state.
        """
        for session_id, s in self.states.items():
            if s == state:
                return session_id
        return None

    def clear_state(self, session_id: str):
        """
        Clear the state for a given session ID.
        """
        if session_id in self.states:
            del self.states[session_id]

sheets_creds_memory = SheetsCredsMemory()
