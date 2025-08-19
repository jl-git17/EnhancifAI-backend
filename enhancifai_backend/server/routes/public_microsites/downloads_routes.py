
import mimetypes
import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse

from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.server.routes.public_microsites.common import verify_session_id
from enhancifai_backend.server.utils import (
    STATIC_FILES_DIRECTORY,
    get_microsite_session_id,
    verify_secret_key
)


router = APIRouter()

@router.get("/microsites/downloads/{filename}", tags=["Microsites - Downloads"])
async def download_file(
    filename: str, 
    _: str = Depends(verify_secret_key),
    session_id: str = Depends(get_microsite_session_id)
):
    try:
        if verify_session_id(session_id) is not True:
            return JSONResponse(status_code=403, content={"detail": "Invalid session ID"})
        file_path = os.path.join('/tmp', filename)
        if os.path.exists(file_path):
            # Guess the MIME type of the file based on its extension
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = "application/octet-stream"  # Use a binary stream as a fallback

            # Extract the file name for use in the Content-Disposition header
            file_name = os.path.basename(file_path)

            return FileResponse(file_path, media_type=mime_type, filename=file_name)
        else:
            raise HTTPException(status_code=404, detail="File not found.")
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Catch-all for unexpected errors
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred", "error": str(e)}
        )
