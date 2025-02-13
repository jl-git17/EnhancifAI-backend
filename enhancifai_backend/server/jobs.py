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
    Deletes files in /tmp directory that are older than FILE_AGE_LIMIT.
    """
    current_time = time.time()
    for filename in os.listdir('/tmp'):
        file_path = os.path.join('/tmp', filename)
        try:
            # Get the file's last modification time
            file_mtime = os.path.getmtime(file_path)
            # Check if the file is older than the specified age limit
            if current_time - file_mtime > FILE_AGE_LIMIT:
                os.remove(file_path)
                print(f"Deleted old file: {file_path}")
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
