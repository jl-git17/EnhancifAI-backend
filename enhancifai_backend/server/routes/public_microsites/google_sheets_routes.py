import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from google_auth_oauthlib.flow import Flow

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.microsites import MicrositesRunsDbCore
from enhancifai_backend.engine.import_google_sheets import GoogleSheetsHandler
from enhancifai_backend.server.models.execution import ExportSheetsRequest
from enhancifai_backend.server.utils import get_current_user_id, verify_secret_key
from enhancifai_backend.engine.export_google_sheets import export_to_google_sheets

router = APIRouter()

# Load client secrets from environment variable
client_secrets_json = settings.google_token_info_auth
if client_secrets_json is None:
    raise ValueError("GOOGLE_TOKEN_INFO_AUTH environment variable not set")

client_secrets = json.loads(client_secrets_json)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]
REDIRECT_URI = settings.google_sheets_redirect_uri
if REDIRECT_URI is None:
    raise ValueError("GOOGLE_SHEETS_REDIRECT_URI environment variable not set")


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

def get_flow(state=None):
    return Flow.from_client_config(
        client_secrets,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )

@router.get("/microsites/sheets/login", tags=["Google Sheets"], operation_id="login_sheets_operation")
async def login_sheets(session_id: str):
    """
    Initiate Google Sheets login and authorization process.

    This endpoint initiates the OAuth2 flow for Google Sheets API. It generates an authorization URL that the user
    needs to visit to grant access to their Google Sheets account.

    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the status of the operation and the authorization URL.

    - **200**: Successfully generated authorization URL.
      - **content**: `{"status": "success", "url": "<Google Sheets Authorization URL>"}`
    - **401**: User not authenticated.
      - **detail**: `{"detail": "User not authenticated"}`
    """
    already_logged_in = SheetsCredsMemory.has_creds(session_id)
    if already_logged_in:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="User has already logged in for Google Sheets usage."
        )

    flow = get_flow()
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')

    # Store state in the database
    SheetsCredsMemory.set_state(session_id, state)


    return JSONResponse(status_code=200, content={"status": "success", "url": authorization_url})


@router.get("/microsites/callback/google/sheets", tags=["Google Sheets"], operation_id="oauth2callback_google_sheets_operation")
async def oauth2callback(request: Request):
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter")

    user_id = SheetsDbCore.get_oauth_state(state)
    session_id = SheetsCredsMemory.get_state(state)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    _url = str(request.url).replace("http://", "https://")
    flow = get_flow(state)
    try:
        flow.fetch_token(authorization_response=_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token fetch failed: {str(e)}")

    creds = flow.credentials

    SheetsDbCore.update_user_google_credentials(user_id, creds)
    SheetsDbCore.delete_oauth_state(state)

    #return RedirectResponse(url="/")
    return "Authentication successful. You can close this window."

@router.post("/microsites/sheets/export", tags=["Google Sheets"], operation_id="export_to_sheets_operation")
async def export_to_sheets(
    req_sheets: ExportSheetsRequest,
    user_id: int = Depends(get_current_user_id),
    _: str = Depends(verify_secret_key)
):
    """
    Export run data to a Google Sheets document.

    This endpoint exports the run data specified by `run_id` in the request body to a Google Sheets document.
    
    - **req_sheets**: The request body containing the `run_id` of the data to be exported.
    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the status of the export operation
        and the URL of the created Google Sheets document if successful.

    - **200**: Successfully processed request.
      - **content**: `{"status": "success", "url": "<Google Sheets URL>"}`
      - **content**: `{"status": "failed", "status_code": 400, "error": "Unsupported file type"}`
      - **content**: `{"status": "failed", "status_code": 403, "error": "User is not authenticated with Google"}`
      - **content**: `{"status": "failed", "status_code": 403, "error": "Invalid Google credentials or access revoked"}`
      - **content**: `{"status": "failed", "status_code": 500, "error": "Failed to create or update the Google Sheet"}`
    - **401**: User not authenticated.
      - **detail**: `{"detail": "User not authenticated"}`
    - **404**: Run not found or file path not available.
      - **detail**: `{"detail": "Run not found or file path not available"}`
    - **500**: Internal server error.
      - **detail**: Error message detailing what went wrong.
    """

    # Check AI consent
    ai_consent = UsersDbCore.check_ai_consent(user_id)
    if ai_consent is False:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )

    file_path = RunsDbCore.get_run_file_url(req_sheets.run_id)
    source_filename = RunsDbCore.get_source_filename(req_sheets.run_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Run not found or file path not available")

    try:
        result = await export_to_google_sheets(user_id, file_path, source_filename)
        if isinstance(result, dict):
            sheet_url = f"https://docs.google.com/spreadsheets/d/{result['spreadsheetId']}"
            return JSONResponse(status_code=200, content={"status": "success", "url": sheet_url})
        elif isinstance(result, HTTPException):
            return JSONResponse(
                status_code=200,
                content={
                    "status": "failed",
                    "status_code": result.status_code,
                    "error": result.detail
                }
            )
    except Exception as e:
        logging.error(f"Error exporting to Google Sheets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get("/microsites/sheets/list", tags=["Google Sheets"], operation_id="list_sheets_operation")
async def list_sheets(
    search_name: Optional[str] = "",
    page: Optional[int] = 1,
    user_id: int = Depends(get_current_user_id),
    _: str = Depends(verify_secret_key)
):
    """
    List and search Google Sheets for the authenticated user with pagination.

    This endpoint lists Google Sheets for the authenticated user, optionally filtering by a search name, with pagination.

    - **search_name**: The name or partial name of the sheet to search for. If empty, all sheets are returned.
    - **page**: The page number to retrieve (default is 1).
    - **page_size**: The number of sheets per page (default is 20).
    - **user_id**: The ID of the authenticated user. This is fetched automatically by dependency injection (`token`).

    Returns a JSON response containing the list of sheets with their names, IDs, and nextPageToken.

    - **200**: Successfully retrieved list of sheets.
      - **content**:
        ```
            {
                "sheets": [{"spreadsheet_id": "<ID>",
                "sheet_name": "<Name>",
                "worksheets": ["<worksheet1>", "<worksheet2>"]}],
                "nextPageToken": "<Token>"
            }
        ```
    """
    # Check AI consent
    ai_consent = UsersDbCore.check_ai_consent(user_id)
    if ai_consent is False:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )

    handler = GoogleSheetsHandler(user_id)
    page_token = None if page == 1 else page
    result = handler.find_sheet(search_name, page_token)
    return JSONResponse(status_code=200, content=result)

@router.get("/microsites/sheets/data", tags=["Google Sheets"], operation_id="get_data_sheets_operation")
async def get_sheet_data(
    sheet_id: str, worksheet_name: str = None,
    user_id: int = Depends(get_current_user_id),
    _: str = Depends(verify_secret_key)
):
    """
    Retrieve the data contained in the specified Google Sheet for the authenticated user.

    This endpoint returns an array of records contained in the specified `sheet_id`.

    - **sheet_id**: The unique ID of the Google Sheet, as retrieved from the `/sheets/list` endpoint.
    - **worksheet_name**: The name of the worksheet within the Google Sheet. If not specified, the first sheet is used.

    Returns a JSON response containing the list of records.

    - **200**: Successfully retrieved the Google Sheet's data.
      - **content**: ``
    """
    # Check AI consent
    ai_consent = UsersDbCore.check_ai_consent(user_id)
    if ai_consent is False:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )

    handler = GoogleSheetsHandler(user_id)
    try:
        result = handler.get_sheet_as_dataframe(sheet_id, worksheet_name)
        # Convert DataFrame to JSON-compatible format
        records = result.astype(str).to_dict(orient='records')
        return JSONResponse(status_code=200, content={
            "message": "Google Sheet data processed successfully.",
            "records": records
        })
    except HTTPException as e:
        raise e
    except Exception as e:
        logging.error(f"Error retrieving Google Sheet data: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
