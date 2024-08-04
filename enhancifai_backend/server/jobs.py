import os
import time
from enhancifai_backend.engine.import_google_sheets import GoogleSheetsHandler
from enhancifai_backend.database.handlers.users import UsersDbCore
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

def refresh_google_sheets_creds():
    start_time = time.time()  # Record the start time
    creds_list = UsersDbCore.get_all_users_with_creds()
    for cred in creds_list:
        try:
            GoogleSheetsHandler(cred['user_id'])
        except Exception as e:
            print(f"Error refreshing Google Sheets creds: (user_id > {cred['user_id']})\n{e}")
    end_time = time.time()  # Record the end time
    duration = end_time - start_time  # Calculate the duration
    human_readable_time = human_readable_duration(duration)
    print(f"refresh_google_sheets_creds started at {time.ctime(start_time)} and took {human_readable_time}")

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
