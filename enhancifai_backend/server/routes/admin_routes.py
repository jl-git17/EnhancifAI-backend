import csv
from datetime import datetime
import io
import os
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from enhancifai_backend.ai.openai_api import PI_DEFAULT_AI_ENGINE, PI_DEFAULT_PROMPT
from enhancifai_backend.database.handlers.admin import PromptsDbCore, ModelPricesDbCore
from enhancifai_backend.database.handlers.run_logs import PromptImproverRunLogsDbCore, RunLogsDbCore
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


async def is_user_admin(_):
    #return UsersDbCore.is_user_admin(user_id)
    return True


@router.get("/admin/dashboard", tags=["Admin"])
async def admin_dashboard(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "admin_dashboard.html"))
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

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

@router.get("/admin/prompt-improver/settings", tags=["Admin"])
async def get_settings(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Fetch the current settings for the prompt and AI engine.
    Return default values if none are found.
    """
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        user_id = int(os.getenv("ADMIN_USER_ID"))  # Get the user ID from the session

        # Fetch the latest prompt for the user
        latest_prompt = PromptsDbCore.get_latest_prompt_by_user(user_id)

        # If no prompt is found, return the default prompt and AI engine
        if not latest_prompt:
            return {
                "prompt": PI_DEFAULT_PROMPT,
                "ai_engine": PI_DEFAULT_AI_ENGINE
            }

        # Return the latest saved prompt and AI engine
        return {
            "prompt": latest_prompt['prompt'],
            "ai_engine": latest_prompt['ai_engine']
        }
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
        user_id = int(os.getenv("ADMIN_USER_ID"))  # Assuming there's a way to get current user ID
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
        user_id = int(os.getenv("ADMIN_USER_ID"))
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
        user_id = int(os.getenv("ADMIN_USER_ID"))
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
    """
        Download run logs as CSV for a particular date/time range, 
        all times in UTC, with default values for the start and end dates.
    """
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

@router.get("/admin/logs/pi_runs/csv", tags=["Admin"])
async def get_prompt_improver_logs_runs_csv(
    start_date: datetime,
    end_date: datetime
):
    """
    Download prompt improver run logs as CSV for a specified date/time range.
    All times are in UTC, with default values for the start and end dates.
    
    Parameters:
    - start_date (datetime): The start of the date range.
    - end_date (datetime): The end of the date range.
    
    Returns:
    - StreamingResponse: A CSV file containing the prompt improver run logs.
    """

    # Uncomment and implement authorization as needed
    # if not user_id or not await is_user_admin(user_id):
    #     raise HTTPException(status_code=403, detail="Unauthorized Access")

    # Retrieve logs from the database
    logs = PromptImproverRunLogsDbCore.retrieve_logs_by_user_and_date_range(
        start_date, end_date
    )

    # Initialize a StringIO buffer and CSV writer
    output = io.StringIO()
    writer = csv.writer(output)

    if logs:
        # Write CSV header using the keys of the first log entry
        writer.writerow(logs[0].keys())

        for log in logs:
            # Format datetime fields as strings
            log['log_timestamp'] = log['log_timestamp'].strftime('%Y-%m-%d %H:%M:%S.%f')
            # Convert time_elapsed from seconds to HH:MM:SS format
            log['time_elapsed'] = seconds_to_hms(float(log['time_elapsed']))
            # Handle empty errors field
            if not log.get('errors'):
                log['errors'] = ""
            # Write the log values as a CSV row
            writer.writerow(log.values())

    # Reset the buffer's position to the beginning
    output.seek(0)

    # Create a StreamingResponse with the CSV data
    response = StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv"
    )
    # Set the Content-Disposition header to prompt file download
    response.headers["Content-Disposition"] = "attachment; filename=prompt_improver_run_logs.csv"

    return response

@router.get("/admin/billing/model-prices", tags=["Admin"])
async def get_model_prices(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        prices = ModelPricesDbCore.get_all_model_prices()
        return {"model_prices": prices}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.post("/admin/billing/model-prices", tags=["Admin"])
async def update_model_prices(
    data: dict = Body(...),
    credentials: HTTPBasicCredentials = Depends(security)
):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        prices = data.get('prices')
        if not prices or not isinstance(prices, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prices data is required."
            )
        for price_data in prices:
            model_name = price_data.get('model_name')
            price_per_token = price_data.get('price_per_token')
            effective_date = price_data.get('effective_date') or datetime.now().date()
            if not model_name or price_per_token is None:
                continue  # Skip invalid entries
            ModelPricesDbCore.update_model_price(model_name, price_per_token, effective_date)
        return {"message": "Model prices updated successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.get("/admin/billing/model-prices/earliest", tags=["Admin"])
async def get_earliest_effective_month(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        earliest = ModelPricesDbCore.get_earliest_effective_month()
        return {"earliest_month": earliest}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/admin/billing/model-prices/{year}/{month}", tags=["Admin"])
async def get_model_prices_for_month(
    year: int,
    month: int,
    credentials: HTTPBasicCredentials = Depends(security)
):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        prices = ModelPricesDbCore.get_model_prices_for_month(year, month)
        return {"model_prices": prices}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
