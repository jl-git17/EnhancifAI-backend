import json
import google.generativeai as genai

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.microsites import MicrositesRunsDbCore

GOOGLE_AI_STUDIO_API_KEY = settings.google_ai_studio_api_key

PROMPT ="""
- You are an assistant with expertise in data analysis and can use your general knowledge to answer.\n
- Focus on providing direct answers to the user's queries based on the JSON data. Do not repeat or mention the JSON data or provide introductory statements in your responses.\n
- Keep responses brief, relevant, and focused on the query at hand.\n
- If unable to process a row or if the query requires information beyond the data, respond appropriately.\n
- Avoid referring to yourself as AI.\n
- Example of a good response: 'OFEV 100mg is commonly prescribed for treating idiopathic pulmonary fibrosis.'
- Another example of a good response: 'Unfortunately, I do not have enough information about the symptoms for which the drug Lyrica Caps 50mg 90s is prescribed.'
"""

genai.configure(api_key=GOOGLE_AI_STUDIO_API_KEY)


class GeminiConnector:
    """
    Manages the connection and requests to the Gemini API using the specified model.

    Attributes:
        model: An instance of the generative model based on the provided model name.
        rate_limit (bool): Flag to enable or disable rate limiting.
    """
    def __init__(self, model='gemini-pro') -> None:
        self.model = genai.GenerativeModel(model)
        self.rate_limit = True

    def process_csv_row(self, columns, rows, query, run_id: int):
        """
        Processes a CSV row by sending a query along with data payload to the Gemini API.

        The method constructs a message containing a custom prompt and the JSON representation
        of the columns and rows, then sends it to the API. It tracks token usage and aborts if
        the run is cancelled.

        Parameters:
            columns (list): The list of column names from the CSV.
            rows (list): The list of rows (data) from the CSV.
            query (str): The query or question regarding the CSV data.
            run_id (int): The identifier for the current run to check for cancellations.

        Returns:
            dict: A dictionary with keys 'content' for the trimmed response text and 'tokens'
            for the total token count used.

        Raises:
            RuntimeError: If the run is cancelled.
        """
        if MicrositesRunsDbCore.is_run_cancelled(run_id):
            raise RuntimeError("Job cancelled.")
        chat = self.model.start_chat(history=[])
        payload = {
                'columns': columns,
                'rows': rows,
            }
        msg = f"```{PROMPT}```\n\n{query}:\n\n```{json.dumps(payload)}```"
        response = chat.send_message(msg)
        tokens = self.model.count_tokens(chat.history).total_tokens
        # Save token usage entry TODO:
        #user_id = RunsDbCore.get_user_id(run_id)
        return {"content": response.text.strip(), "tokens": tokens}
