from datetime import datetime, timedelta
from enhancifai_backend.database.access import read_db, write_db
from enhancifai_backend.database.handlers.utils import schemafy

class RunLogsDbCore:
    """
    A class used to handle the operations related to run logs in the database.
    """

    @classmethod
    def insert_log(
        cls, run_id, user_name, engine_model, log_timestamp, num_rows_processed,
        num_rows_in_file, num_prompts, num_tokens, errors, time_elapsed, filename,
        overflow, batched=False
        ):
        """
        Insert a log entry into the run_logs table.

        Parameters:
        run_id (str): The ID of the run.
        user_name (str): The name of the user.
        engine_model (str): The engine model used.
        log_timestamp (datetime): The timestamp of the log.
        num_rows_processed (int): Number of rows processed.
        num_rows_in_file (int): Number of rows in the file.
        num_prompts (int): Number of prompts.
        num_tokens (int): Number of tokens.
        errors (str): Errors encountered during the run.
        time_elapsed (float): Time elapsed during the run.
        filename (str): Name of the file processed.
        overflow (bool): Indicates if there was an overflow.
        batched (bool, optional): Indicates if the processing was batched. Defaults to False.

        Returns:
        Any: Result of the write_db operation.
        """
        sql = schemafy("""
            INSERT INTO enhancifai.run_logs (
                       run_id, user_name, engine_model, log_timestamp,
                       num_rows_processed, num_rows_in_file, num_prompts,
                       num_tokens, errors, time_elapsed, filename, overflow, batched)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """)
        return write_db.do(
            'execute', sql=sql, data=(
                run_id, user_name, engine_model, log_timestamp,
                num_rows_processed, num_rows_in_file, num_prompts,
                num_tokens, errors, time_elapsed, filename, overflow, batched
            )
        )

    @classmethod
    def retrieve_logs_by_date_range(cls, start, end=None):
        """
        Retrieve logs within a specified date range.

        Parameters:
        start (datetime or str): The start date of the range.
        end (datetime or str, optional): The end date of the range. Defaults to None.

        Returns:
        list: A list of logs within the specified date range.
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
        user_id (int): The ID of the user.
        engine_model (str): The engine model used.
        log_timestamp (datetime): The timestamp of the log.
        time_elapsed (float): Time elapsed during the run.
        num_prompts (int): Number of prompts.
        num_tokens (int): Number of tokens.
        errors (str, optional): Errors encountered during the run. Defaults to None.

        Returns:
        Any: Result of the write_db operation.
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
        Retrieve logs for a specific user within a specified date range.

        Parameters:
        user_id (int): The ID of the user.
        start (datetime or str): The start date of the range.
        end (datetime or str, optional): The end date of the range. Defaults to None.

        Returns:
        list: A list of logs within the specified date range for the user.
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
        Retrieve logs within a specified date range from the prompt_improver_run_logs table,
        without filtering by user.

        Parameters:
        start (datetime or str): The start date of the range.
        end (datetime or str, optional): The end date of the range. Defaults to None.

        Returns:
        list: A list of logs within the specified date range.
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

