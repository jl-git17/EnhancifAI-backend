import logging
import os
import time

from enhancifai_backend.server.utils import FILE_AGE_LIMIT

def human_readable_duration(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{int(hours)} hours, {int(minutes)} minutes, and {seconds:.2f} seconds"
    elif minutes > 0:
        return f"{int(minutes)} minutes and {seconds:.2f} seconds"
    else:
        return f"{seconds:.2f} seconds"

def delete_old_files():
    """
    Deletes files in /tmp/enhancifai_cache directory that are older than FILE_AGE_LIMIT.
    """
    target_dir = '/tmp/enhancifai_cache'
    current_time = time.time()
    if not os.path.exists(target_dir):
        logging.warning(f"Directory {target_dir} does not exist.")
        return
    for filename in os.listdir(target_dir):
        file_path = os.path.join(target_dir, filename)
        try:
            # Only process files, not subdirectories
            if os.path.isfile(file_path):
                file_mtime = os.path.getmtime(file_path)
                if current_time - file_mtime > FILE_AGE_LIMIT:
                    os.remove(file_path)
        except Exception as e:
            logging.error(f"Error deleting file {file_path}: {e}")
