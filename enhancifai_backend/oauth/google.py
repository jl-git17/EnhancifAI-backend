# pylint: disable=import-error
import logging
from google_auth_oauthlib.flow import Flow
import requests

from enhancifai_backend.config import settings

SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email']

class GoogleAuthenticator:
    def __init__(self):
        self.accounts = {}

    def _get_flow(self):
        return Flow.from_client_config(
            settings.google_token_info_auth,
            SCOPES,
            redirect_uri=settings.google_sheets_redirect_uri
        )

    def authenticate_url(self):
        flow = self._get_flow()
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url

    def fetch_token(self, code, state):
        flow = Flow.from_client_config( # type: ignore
            settings.google_token_info_auth, SCOPES, state=state, redirect_uri=settings.google_sheets_redirect_uri
        )
        _ = flow.fetch_token(code=code)

        user_info = self.get_user_info(flow.credentials)
        return user_info

    def get_user_info(self, creds):
        """Fetch the email of the authenticated user."""
        url = 'https://www.googleapis.com/oauth2/v1/userinfo'
        response = requests.get(url, headers={'Authorization': f'Bearer {creds.token}'}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            logging.error("Failed to fetch user info: %s, %s", response.status_code, response.text)
            print(f"Failed to fetch user info: {response.status_code}, {response.text}")
            return None


google_auth = GoogleAuthenticator()
