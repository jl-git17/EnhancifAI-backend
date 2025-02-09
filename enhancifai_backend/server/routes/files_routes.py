

import os
import shutil
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.server.models.execution import CacheRequest
from enhancifai_backend.server.utils import get_current_user_id, verify_secret_key


CACHE_DIRECTORY = '/tmp/cache'

router = APIRouter()

def ensure_cache_directory():
    if not os.path.exists(CACHE_DIRECTORY):
        os.makedirs(CACHE_DIRECTORY)

def get_cache_file_path(user_id, filename):
    ensure_cache_directory()
    user_dir = os.path.join(CACHE_DIRECTORY, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, filename)

def save_to_cache(file_path, user_id, filename):
    cache_path = get_cache_file_path(user_id, filename)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    shutil.copy(file_path, cache_path)
    return cache_path

def get_from_cache(user_id, filename):
    cache_path = get_cache_file_path(user_id, filename)
    if os.path.exists(cache_path):
        return cache_path
    return None


@router.post("/cache/download", tags=["Cache"])
async def get_cached_file(
    req: CacheRequest,
    _: str = Depends(verify_secret_key),
    user_id: int = Depends(get_current_user_id)
):
    # Check AI consent
    ai_consent = UsersDbCore.check_ai_consent(user_id)
    if ai_consent is False:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )
    cache_path = get_from_cache(user_id, req.filename)
    if cache_path and os.path.exists(cache_path):
        return FileResponse(cache_path)
    else:
        raise HTTPException(status_code=404, detail="File not found in cache or database")

@router.post("/cache/upload", tags=["Cache"])
async def add_cached_file(
    data_file: UploadFile = File(...),
    _: str = Depends(verify_secret_key),
    user_id: int = Depends(get_current_user_id)
):
    # Check AI consent
    ai_consent = UsersDbCore.check_ai_consent(user_id)
    if ai_consent is False:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="User has not consented for AI usage."
        )
    # Determine the suffix for the file based on its content type
    file_suffix_map = {
        'text/csv': '.csv',
        'application/vnd.ms-excel': '.xls',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx'
    }
    data_file_suffix = file_suffix_map.get(data_file.content_type, None)
    temp_data_file_path = None

    if not data_file_suffix:
        raise HTTPException(status_code=400, detail="Invalid data file type")
    # Handling Data File
    with NamedTemporaryFile(delete=False, dir='/tmp', suffix=data_file_suffix) as temp_data_file:
        temp_data_file_path = temp_data_file.name
        data_contents = await data_file.read()
        temp_data_file.write(data_contents)
        temp_data_file.flush()
    # Save file to cache
    save_to_cache(temp_data_file_path, user_id, data_file.filename)
