

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.server.models.execution import CacheRequest


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
    os.rename(file_path, cache_path)
    return cache_path

def get_from_cache(user_id, filename):
    cache_path = get_cache_file_path(user_id, filename)
    if os.path.exists(cache_path):
        return cache_path
    return None


@router.post("/files/cache", tags=["Files"])
async def get_cached_file(request: CacheRequest):
    cache_path = get_from_cache(request.user_id, request.filename)
    if cache_path and os.path.exists(cache_path):
        return FileResponse(cache_path)
    else:
        # Check if the file exists in the database
        file_url = RunsDbCore.get_run_file_url(request.run_id)
        if file_url:
            return FileResponse(file_url)
        else:
            raise HTTPException(status_code=404, detail="File not found in cache or database")
