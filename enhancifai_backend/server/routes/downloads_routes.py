
import mimetypes
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse

from enhancifai_backend.server.utils import STATIC_FILES_DIRECTORY, get_current_user_id, verify_secret_key


router = APIRouter()

@router.get("/downloads/prompts-template", tags=["Downloads"])
async def download_prompts_template(_: str = Depends(verify_secret_key)):
    """Download the prompt template file."""
    try:
        file_path = os.path.join(STATIC_FILES_DIRECTORY, "prompts_template.xlsx")
        if os.path.exists(file_path):
            return FileResponse(file_path, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename="prompts_template.xlsx")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Prompts template file is unavailable at the moment."
            )
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})
    
@router.get("/downloads/{filename}", tags=["Downloads"])
async def download_file(filename: str, _: str = Depends(verify_secret_key), 
                        user_id: Optional[int] = Depends(get_current_user_id)):
    try:
        file_path = os.path.join('/tmp', filename)
        if os.path.exists(file_path):
            # Guess the MIME type of the file based on its extension
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = "application/octet-stream"  # Use a binary stream as a fallback MIME type

            # Extract the file name for use in the Content-Disposition header
            file_name = os.path.basename(file_path)

            return FileResponse(file_path, media_type=mime_type, filename=file_name)
        else:
            raise HTTPException(status_code=404, detail="File not found.")
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred", "error": str(e)})