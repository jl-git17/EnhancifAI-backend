import json
import os
import google.generativeai as genai

from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore

GOOGLE_AI_STUDIO_API_KEY = os.getenv('GOOGLE_AI_STUDIO_API_KEY')

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
    """Class to manage connections and requests to Gemini API."""

    def __init__(self, model='gemini-pro') -> None:
        self.model = genai.GenerativeModel(model)
        self.rate_limit = True

    def process_csv_row(self, columns, rows, query, run_id: int):
        if RunsDbCore.is_run_cancelled(run_id):
            raise RuntimeError("Job cancelled.")
        chat = self.model.start_chat(history=[])
        payload = {
                'columns': columns,
                'rows': rows,
            }
        msg = f"```{PROMPT}```\n\n{query}:\n\n```{json.dumps(payload)}```"
        response = chat.send_message(msg)
        tokens = self.model.count_tokens(chat.history).total_tokens
        # Save token usage entry
        user_id = RunsDbCore.get_user_id(run_id)
        UsersDbCore.add_token_usage(user_id, 'gemini-pro', tokens)
        return {"content": response.text.strip(), "tokens": tokens}
