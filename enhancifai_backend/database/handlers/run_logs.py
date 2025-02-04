from datetime import datetime, timedelta
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class RunLogsDbCore:
    """
    A class to handle run log operations in the database.
    """

    @classmethod
    def insert_log(
        cls, run_id, user_name, engine_model, log_timestamp, num_rows_processed,
        num_rows_in_file, num_prompts, input_tokens, output_tokens, errors, time_elapsed, filename,
        overflow, batched=False
        ):
        """
        Insert a log entry into the run_logs table.

        Parameters:
            run_id (str): Unique identifier for the run.
            user_name (str): Name of the user.
            engine_model (str): Engine model used.
            log_timestamp (datetime): Timestamp when the log was created.
            num_rows_processed (int): Count of processed rows.
            num_rows_in_file (int): Total rows in the file.
            num_prompts (int): Number of prompts executed.
            input_tokens (int): Number of input tokens processed.
            output_tokens (int): Number of output tokens processed.
            errors (str): Any errors encountered.
            time_elapsed (float): Time taken for the run.
            filename (str): Name of the processed file.
            overflow (bool): Indicates if an overflow occurred.
            batched (bool, optional): True if processed in batches. Defaults to False.

        Returns:
            Result from write_db.do operation.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.run_logs (
                       run_id, user_name, engine_model, log_timestamp,
                       num_rows_processed, num_rows_in_file, num_prompts, input_tokens, output_tokens,
                       errors, time_elapsed, filename, overflow, batched)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """)
        return write_db.do(
            'execute', sql=sql, data=(
                run_id, user_name, engine_model, log_timestamp,
                num_rows_processed, num_rows_in_file, num_prompts, input_tokens, output_tokens,
                errors, time_elapsed, filename, overflow, batched
            )
        )

    @classmethod
    def retrieve_logs_by_date_range(cls, start, end=None):
        """
        Retrieve logs within a specified date range.

        Parameters:
            start (datetime or str): Start date/time of the range.
            end (datetime or str, optional): End date/time; defaults to one day after start if not provided.

        Returns:
            List of run logs sorted by log_id.
        """
        # Convert start to a datetime object if not already
        if not isinstance(start, datetime):
            start = datetime.fromisoformat(str(start))

        # If end is None, set it to 'start' + 1 day; otherwise, convert it to datetime
        if end is None:
            end = start + timedelta(days=1)
        elif not isinstance(end, datetime):
            end = datetime.fromisoformat(str(end))

        # Adjust 'end' time to the end of the day if it originally had no time part
        # (i.e., is at midnight of the given end date)
        if end.time() == datetime.min.time():
            end = datetime.combine(end, datetime.max.time())

        sql = schemafy("""
            SELECT rl.*, r.source_type 
            FROM enhancifai.run_logs rl
            JOIN enhancifai.runs r ON rl.run_id = r.id
            WHERE rl.log_timestamp BETWEEN %s AND %s
            ORDER BY rl.log_id;
        """)
        return read_db.do('select', sql=sql, data=(start, end)) or []

class PromptImproverRunLogsDbCore:
    @classmethod
    def insert_log(cls, user_id, engine_model, log_timestamp, time_elapsed, num_prompts, num_tokens, errors=None):
        """
        Insert a log entry into the prompt_improver_run_logs table.

        Parameters:
            user_id (int): User identifier.
            engine_model (str): Engine model used.
            log_timestamp (datetime): Timestamp of the log entry.
            time_elapsed (float): Duration of the run.
            num_prompts (int): Count of prompts executed.
            num_tokens (int): Number of tokens processed.
            errors (str, optional): Errors encountered, if any.

        Returns:
            Result from write_db.do operation.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.prompt_improver_run_logs (
                user_id, engine_model, log_timestamp,
                time_elapsed, num_prompts,
                num_tokens, errors)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """)
        return write_db.do(
            'execute', sql=sql, data=(
                user_id, engine_model, log_timestamp,
                time_elapsed, num_prompts,
                num_tokens, errors
            )
        )

    @classmethod
    def retrieve_logs_by_user_and_date_range(cls, user_id, start, end=None):
        """
        Retrieve logs for a specific user within a date range.

        Parameters:
            user_id (int): User identifier.
            start (datetime or str): Start date/time of the range.
            end (datetime or str, optional): End date/time; defaults to one day after start if not provided.

        Returns:
            List of user-specific logs sorted by log_id.
        """
        # Convert start to a datetime object if not already
        if not isinstance(start, datetime):
            start = datetime.fromisoformat(str(start))

        # If end is None, set it to 'start' + 1 day; otherwise, convert it to datetime
        if end is None:
            end = start + timedelta(days=1)
        elif not isinstance(end, datetime):
            end = datetime.fromisoformat(str(end))

        # Adjust 'end' time to the end of the day if it originally had no time part
        # (i.e., is at midnight of the given end date)
        if end.time() == datetime.min.time():
            end = datetime.combine(end, datetime.max.time())

        sql = schemafy("""
            SELECT * 
            FROM enhancifai.prompt_improver_run_logs
            WHERE user_id = %s AND log_timestamp BETWEEN %s AND %s
            ORDER BY log_id;
        """)
        return read_db.do('select', sql=sql, data=(user_id, start, end)) or []

    @classmethod
    def retrieve_logs_by_date_range(cls, start, end=None):
        """
        Retrieve all logs within a specified date range.

        Parameters:
            start (datetime or str): Start date/time of the range.
            end (datetime or str, optional): End date/time; defaults to one day after start if not provided.

        Returns:
            List of logs sorted by log_id.
        """
        # Convert start to a datetime object if not already
        if not isinstance(start, datetime):
            start = datetime.fromisoformat(str(start))

        # If end is None, set it to 'start' + 1 day; otherwise, convert to datetime
        if end is None:
            end = start + timedelta(days=1)
        elif not isinstance(end, datetime):
            end = datetime.fromisoformat(str(end))

        # Adjust 'end' time to the end of the day if originally at midnight
        if end.time() == datetime.min.time():
            end = datetime.combine(end, datetime.max.time())

        sql = schemafy("""
            SELECT * 
            FROM enhancifai.prompt_improver_run_logs
            WHERE log_timestamp BETWEEN %s AND %s
            ORDER BY log_id;
        """)
        return read_db.do('select', sql=sql, data=(start, end)) or []
