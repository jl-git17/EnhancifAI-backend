import json
import os
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.admin import AISettingsDbCore
from enhancifai_backend.database.handlers.microsites import MicrositeFunctionsDbCore
from enhancifai_backend.server.models.admin import AdminAISettings
from enhancifai_backend.server.utils import STATIC_PAGES_DIRECTORY, get_current_user_id, verify_secret_key, AdminSettings


USERNAME = settings.admin_username
PASSWORD = settings.admin_password


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

# --- Microsite Functions CRUD Endpoints ---
@router.get("/admin/public-microsites/functions", tags=["Admin"])
async def get_microsite_functions(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        functions = MicrositeFunctionsDbCore.get_all_functions()
        # Convert prompts from JSON string to list if needed
        for fn in functions:
            if isinstance(fn.get("prompts"), str):
                try:
                    fn["prompts"] = json.loads(fn["prompts"])
                except Exception:
                    fn["prompts"] = []
        return functions
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.get("/admin/public-microsites/functions/{function_id}", tags=["Admin"])
async def get_microsite_function(function_id: int, credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        fn = MicrositeFunctionsDbCore.get_function_by_id(function_id)
        if not fn:
            raise HTTPException(status_code=404, detail="Function not found.")
        if isinstance(fn.get("prompts"), str):
            try:
                fn["prompts"] = json.loads(fn["prompts"])
            except Exception:
                fn["prompts"] = []
        return fn
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.post("/admin/public-microsites/functions", tags=["Admin"])
async def create_microsite_function(payload: dict = Body(...), credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        function_name = payload.get("function_name")
        prompts = payload.get("prompts")
        if not function_name or not prompts:
            raise HTTPException(status_code=400, detail="Function name and prompts are required.")
        # Store prompts as JSON string
        prompts_json = json.dumps(prompts)
        try:
            new_id = MicrositeFunctionsDbCore.create_function(function_name, prompts_json)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"id": new_id}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.put("/admin/public-microsites/functions/{function_id}", tags=["Admin"])
async def update_microsite_function(function_id: int, payload: dict = Body(...), credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        function_name = payload.get("function_name")
        prompts = payload.get("prompts")
        if not function_name or not prompts:
            raise HTTPException(status_code=400, detail="Function name and prompts are required.")
        prompts_json = json.dumps(prompts)
        try:
            updated = MicrositeFunctionsDbCore.update_function(function_id, function_name=function_name, prompt=prompts_json)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return updated
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.delete("/admin/public-microsites/functions/{function_id}", tags=["Admin"])
async def delete_microsite_function(function_id: int, credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        MicrositeFunctionsDbCore.delete_function(function_id)
        return {"message": "Function deleted successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


# New: Public Microsites Management Page
@router.get("/admin/dashboard/public-microsites", tags=["Admin"])
async def admin_public_microsites(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        return FileResponse(os.path.join(STATIC_PAGES_DIRECTORY, "public_microsites.html"))
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

@router.post("/admin/ai-settings", tags=["Admin"])
async def set_admin_settings_ai(settings_admin_ai:AdminAISettings, _: str = Depends(verify_secret_key),
                                __: int = Depends(get_current_user_id)):
    """Set the Admin settings for AI."""
    # TODO: check if user is an admin
    AdminSettings.set_ai_settings(engine=settings_admin_ai.ai_engine.value, api_key=settings_admin_ai.api_key)
    return JSONResponse(status_code=200, content={"message": "Success."})

# New: Retrieve current AI settings
@router.get("/admin/ai/settings", tags=["Admin"])
async def get_admin_ai_settings(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        ai_settings = AISettingsDbCore.get_ai_settings()
        return JSONResponse(status_code=200, content=ai_settings)
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )

# New: Update AI settings
@router.post("/admin/ai/settings", tags=["Admin"])
async def set_admin_ai_settings(
    payload: dict = Body(...),
    credentials: HTTPBasicCredentials = Depends(security)
):
    """
    Set the Admin AI settings (stub - implement functionality yourself)
    """
    if credentials.username == USERNAME and credentials.password == PASSWORD:
        # payload may contain e.g. {"temperature": "0.7"} etc.
        AISettingsDbCore.update_ai_settings(**payload)
        return JSONResponse(status_code=200, content={"message": "AI settings updated successfully"})
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
