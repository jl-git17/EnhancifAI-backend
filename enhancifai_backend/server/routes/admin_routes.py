import csv
from datetime import datetime
import io
import os
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from enhancifai_backend.ai.openai_api import pi_settings
from enhancifai_backend.database.handlers.admin import PromptsDbCore
from enhancifai_backend.database.handlers.run_logs import RunLogsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.server.models.admin import AdminAISettings, RunLogsRequest
from enhancifai_backend.server.utils import STATIC_PAGES_DIRECTORY, get_current_user_id, verify_secret_key, AdminSettings


USERNAME = os.getenv('ADMIN_USERNAME')
PASSWORD = os.getenv('ADMIN_PASSWORD')

router = APIRouter()
security = HTTPBasic()

def seconds_to_hms(seconds):
    """Converts seconds to a formatted string 'hh:mm:ss'."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{int(hours):02}:{int(minutes):02}:{seconds:06.3f}"


async def is_user_admin(user_id):
    return UsersDbCore.is_user_admin(user_id)

@router.post("/admin/ai-settings", tags=["Admin"])
async def set_admin_settings_ai(settings:AdminAISettings, _: str = Depends(verify_secret_key),
                                __: int = Depends(get_current_user_id)):
    """Set the Admin settings for AI."""
    # TODO: check if user is an admin
    AdminSettings.set_ai_settings(engine=settings.ai_engine.value, api_key=settings.api_key)
    return JSONResponse(status_code=200, content={"message": "Success."})

@router.get("/admin/prompt-improver", tags=["Admin"])
async def admin_prompt_improver(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "pi_admin.html"))
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )



@router.get("/admin/prompt-improver/prompts", tags=["Admin"])
async def get_prompt_versions(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Fetch all versions of prompts for the current user.
    """
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        user_id = get_current_user_id()  # Assuming there's a way to get current user ID
        prompts = PromptsDbCore.get_prompt_versions_by_user(user_id)
        return {"prompts": prompts}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/admin/prompt-improver/prompts/{version}", tags=["Admin"])
async def get_prompt_by_version(version: int, credentials: HTTPBasicCredentials = Depends(security)):
    """
    Fetch a specific version of a prompt.
    """
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        user_id = get_current_user_id()
        prompt = PromptsDbCore.get_prompt_by_version(user_id, version)
        if prompt:
            return prompt
        else:
            raise HTTPException(status_code=404, detail="Prompt not found.")
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    

@router.post("/admin/prompt-improver/settings", tags=["Admin"])
async def update_settings(
    data: dict = Body(...),
    credentials: HTTPBasicCredentials = Depends(security)
):
    """
    Save the current prompt as a new version.
    """
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        prompt = data.get('prompt')
        ai_engine = data.get('ai_engine')

        if not prompt or not ai_engine:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt and AI Engine are required."
            )
        
        # Save the new prompt version
        user_id = get_current_user_id()
        PromptsDbCore.save_new_prompt(user_id, prompt, ai_engine)

        return {"message": "Settings updated successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/admin/logs", tags=["Admin"])
async def admin_logs(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "download_logs.html"))
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.post("/admin/logs/runs", tags=["Admin"])
async def get_logs_runs(logs_request: RunLogsRequest, _: str = Depends(verify_secret_key),
                        user_id: Optional[int] = Depends(get_current_user_id)):
    """Get run logs for a particular date/time range all times in UTC."""
    if not user_id or not await is_user_admin(user_id):  # Assuming is_user_admin is implemented
        raise HTTPException(status_code=403, detail="Unauthorized Access")

    # Assuming the retrieve_logs_by_date_range expects datetime in UTC
    logs = RunLogsDbCore.retrieve_logs_by_date_range(
        logs_request.start_date, logs_request.end_date)
    return logs

@router.get("/admin/logs/runs/csv", tags=["Admin"])
async def get_logs_runs_csv(
    start_date: datetime,
    end_date: datetime
):
    """Download run logs as CSV for a particular date/time range, all times in UTC, with default values for the start and end dates."""
    #if not user_id or not await is_user_admin(user_id):
        #raise HTTPException(status_code=403, detail="Unauthorized Access")

    logs = RunLogsDbCore.retrieve_logs_by_date_range(
        start_date, end_date
    )
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if logs:
        writer.writerow(logs[0].keys())
        for log in logs:
            # Convert the datetime object to a string
            log['log_timestamp'] = log['log_timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')
            log['time_elapsed'] = seconds_to_hms(float(log['time_elapsed']))
            if log['errors'] == []:
                log['errors'] = ""
            writer.writerow(log.values())
    
    output.seek(0)
    
    response = StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv"
    )
    response.headers["Content-Disposition"] = "attachment; filename=run_logs.csv"
    
    return response
