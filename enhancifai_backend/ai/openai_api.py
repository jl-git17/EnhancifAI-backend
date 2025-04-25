import json
import os
import re
import time
import logging
from typing import Dict, List

from fastapi import HTTPException
from openai import OpenAI

from enhancifai_backend.config import settings
from enhancifai_backend.database.handlers.runs import RunsDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.database.handlers.admin import PromptsDbCore
from enhancifai_backend.engine.rate_limit_manager import rate_limit_manager

BUFFER_MULTIPLIER = 2

RATE_LIMIT_PATTERN = re.compile(r'Please try again in ([\d\.]+)s')

PI_DEFAULT_PROMPT = (
    "Please review and improve the prompt for clarity, effectiveness, and engagement. "
    "Make sure the prompt takes the role of an expert in the relevant field. "
    "Feel free to enhance the wording, structure, and tone as needed."
)
PI_DEFAULT_AI_ENGINE = "gpt-4.1-nano"
ADMIN_USER_ID = settings.admin_user_id

DEFAULT_PROMPT = (
    "- You are an assistant with expertise in data analysis and can use your general knowledge "
    "to answer.\n"
    "- Focus on providing direct answers to the user's queries based on the JSON data. "
    "Do not repeat or mention the JSON data or provide introductory statements in your responses.\n"
    "- Keep responses brief, relevant, and focused on the query at hand.\n"
    "- If unable to process a row or if the query requires information beyond the data, "
    "respond appropriately.\n"
    "- Avoid referring to yourself as AI.\n"
    "- Example of a good response: 'OFEV 100mg is commonly prescribed for treating idiopathic "
    "pulmonary fibrosis.'"
    "- Another example of a good response: 'Unfortunately, I do not have enough information "
    "about the symptoms for which the drug Lyrica Caps 50mg 90s is prescribed.'"
)

DEFAULT_PROMPT_BATCHED = json.dumps({
  "input_format":{"query":"string","payload":{"columns":"object","rows":"array"}},
  "instructions":{
    "task":"Generate concise text per row using the query. Return a valid JSON array with one item per row.",
    "handling_incomplete_data":{"rule":"If data missing, return 'Incomplete data'."},
    "rules":["Include all rows.","Be concise.","No intros or repeats.","Output only JSON array."]
  },
  "example":{
    "input":{
      "query":"Format churn risk as 'Risk: <value>'.",
      "payload":{
        "columns":{"A":"ID","E":"Churn"},
        "rows":[{"A":"1","E":"5"},{"A":"2","E":"4"},{"A":"3","E":"5"},{"A":"4","E":"3"},{"A":"5","E":""}]
      }
    },
    "output":["Risk: High","Risk: Medium","Risk: High","Risk: Low","Risk: Incomplete data"]
  }
})


def extract_and_parse_json(raw_data):
    """
    Extracts JSON content from raw data which may or may not be wrapped in Markdown code blocks.
    
    Args:
        raw_data (str): The raw input string containing JSON data.
    
    Returns:
        list: The parsed JSON array.
    
    Raises:
        ValueError: If JSON parsing fails or the parsed data is not a list.
    """
    # Regular expression pattern to match JSON within ```json code blocks
    code_block_pattern = r'```json\s*\n(.*?)\n```'

    # Attempt to find JSON within code blocks
    match = re.search(code_block_pattern, raw_data, re.DOTALL | re.IGNORECASE)

    if match:
        json_str = match.group(1).strip()
        logging.debug("Extracted JSON from code block.")
    else:
        # If no code block is found, assume the entire raw_data is JSON
        json_str = raw_data.strip()
        logging.debug("No code block detected. Using entire raw_data as JSON.")

    try:
        # Parse the JSON string
        parsed = json.loads(json_str)

        # Validate that the parsed data is a list
        if not isinstance(parsed, list):
            raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}.\nContent: {json_str}")

        return parsed

    except json.JSONDecodeError as jde:
        raise ValueError(f"JSON decoding failed: {jde.msg}\nContent: {json_str}") from jde


class PromptImproverSettings:
    def __init__(self, prompt: str=PI_DEFAULT_PROMPT, ai_engine: str=PI_DEFAULT_AI_ENGINE):
        self._prompt = prompt
        self._ai_engine = ai_engine
        self._update_from_db()

    def _update_from_db(self):
        try:
            from_db = PromptsDbCore.get_latest_prompt_by_user(ADMIN_USER_ID)
            if from_db:
                self._prompt = from_db['prompt']
                self._ai_engine = from_db['ai_engine']
        except Exception as e:
            logging.error(e)

    # Getter for prompt
    @property
    def prompt(self):
        self._update_from_db()
        return self._prompt

    # Setter for prompt
    @prompt.setter
    def prompt(self, value: str):
        self._prompt = value

    # Getter for ai_engine
    @property
    def ai_engine(self):
        self._update_from_db()
        return self._ai_engine

    # Setter for ai_engine
    @ai_engine.setter
    def ai_engine(self, value: str):
        self._ai_engine = value

pi_settings = PromptImproverSettings(prompt=PI_DEFAULT_PROMPT, ai_engine=PI_DEFAULT_AI_ENGINE)


class OpenAIConnector:
    """Class to manage connections and requests to OpenAI API."""

    def __init__(self, engine) -> None:
        self.engine = engine
        #self.temperature = temperature
        #self.top_p = top_p
        # Initialize OpenAI client with API key
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.rate_limit = False

    def process_csv_row(self, columns: list, rows: dict, query: str, run_id: int) -> dict:
        """
        Process a CSV row with specified columns and query using OpenAI API.

        :param columns: List of column headers.
        :param row: List of row data.
        :param query: String containing specific processing directives.
        :return: Dictionary with processed content and token usage.
        """
        if RunsDbCore.is_run_cancelled(run_id):
            raise RuntimeError("Job cancelled.")
        payload = {
            'columns': columns,
            'rows': rows,
        }

        max_attempts = 3
        _err = None

        # Check rate limit manager
        self.engine = rate_limit_manager.can_make_api_call(model=self.engine,run_id=run_id)
        #logging.debug(f"Got engine from rlm: {self.engine}")

        for attempt in range(max_attempts):
            try:
                messages = [
                    {
                        "role": "system",
                        "content": DEFAULT_PROMPT
                    },
                    {
                        "role": "assistant",
                        "content": "Ready to assist with your queries. Please provide your question."
                    }
                ]

                # User's query and payload are appended here
                messages.append(
                    {
                        "role": "user",
                        "content": f"{query}:\n\n```{json.dumps(payload)}```"
                    }
                )


                completion = self.client.chat.completions.create(
                    model=self.engine,
                    messages=messages,
                    temperature=0.5,
                    #temperature=self.temperature,
                    #top_p=self.top_p
                )

                data = completion.choices[0].message.content
                tokens_used = completion.usage.total_tokens
                input_tokens = completion.usage.prompt_tokens
                output_tokens = tokens_used - input_tokens

                # Update rate limit manager
                rate_limit_manager.update_make_api_call(self.engine, tokens_used=tokens_used)

                if 'SYS:NONE' in data:
                    data = data.replace('SYS:NONE', '').strip()

                # Save token usage entry
                user_id = RunsDbCore.get_user_id(run_id)
                UsersDbCore.add_user_token_usage(user_id, run_id, self.engine, tokens_used)

                return {
                    "content": data.strip(),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "engine_used": self.engine
                }

            except Exception as e:
                logging.error(e)
                if getattr(e, 'status_code', None) == 429:
                    try:
                        # Use the compiled pattern to search the string
                        match = RATE_LIMIT_PATTERN.search(e.body['message'])
                        # Extract the number of seconds
                        if match:
                            delay = float(match.group(1))
                        else:
                            delay = 5
                    except (ValueError, IndexError):
                        delay = 5  # Default to 5 seconds if parsing fails

                    sleep_time = delay * BUFFER_MULTIPLIER  # Add a buffer time
                    logging.debug(f"Rate limit exceeded. Waiting for {sleep_time} seconds before retrying...")
                    time.sleep(sleep_time)
                else:
                    logging.error(f"OpenAI API error on attempt {attempt + 1}: {e}")
                    _err = e
                    if attempt < max_attempts - 1:
                        # Exponential backoff with a base delay of 1 second
                        time.sleep(1 * (2 ** attempt))


        if _err is None:
            raise RuntimeError("Failed to get answer from OpenAI API after 3 attempts.")
        else:
            logging.error("Failed to get answer from OpenAI API after 3 attempts.")
            return {'content': _err, 'tokens': 0}

    def process_csv_rows(
        self,
        columns: Dict[str, str],
        rows: List[Dict[str, str]],
        query: str,
        run_id: int
    ) -> List[Dict[str, object]]:

        if RunsDbCore.is_run_cancelled(run_id):
            raise RuntimeError("Job cancelled.")

        max_attempts = 3
        _err = None

        logging.info("Query: %s  \nRows: %s  \nColumns: %s", query, rows, columns)

        # Use the same logic your single-row method uses:
        self.engine = rate_limit_manager.can_make_api_call(model=self.engine, run_id=run_id)

        for attempt in range(max_attempts):
            try:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            'Process each DATA entry based on the query. Return results as a JSON array (["answer string","answer string"]). '
                            "One concise string for each DATA entry's full answer, in plain text format unless the query explicitly instructs otherwise."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Query: {query}\n"
                            "---\n"
                            "DATA:\n"
                            f"{json.dumps(rows)}"
                        )
                    }
                ]

                logging.debug(f"MODEL: {self.engine}")

                completion = self.client.chat.completions.create(
                    model=self.engine,
                    messages=messages,
                    #response_format={"type": "json_object"}
                    temperature=0.2
                )

                raw_data = completion.choices[0].message.content

                logging.debug(f"Raw data: {raw_data}")

                tokens_used = completion.usage.total_tokens
                input_tokens = completion.usage.prompt_tokens
                output_tokens = tokens_used - input_tokens

                # Rate limit manager housekeeping
                rate_limit_manager.update_make_api_call(self.engine, tokens_used=tokens_used)

                user_id = RunsDbCore.get_user_id(run_id)
                UsersDbCore.add_user_token_usage(user_id, run_id, self.engine, tokens_used)

                try:
                    # strip the code block markers if they exist
                    raw_data = raw_data.strip()
                    if raw_data.startswith("```json") and raw_data.endswith("```"):
                        raw_data = raw_data[7:-3].strip('```json').strip('```').strip('\n')
                    elif raw_data.startswith("```") and raw_data.endswith("```"):
                        raw_data = raw_data[3:-3].strip('```').strip('\n')

                    _results = json.loads(raw_data)
                    if not isinstance(_results, list):
                        logging.error("Unexpected JSON structure:", type(_results))
                        return
                    # Build the output. Each row gets a dict with the concatenated answers
                    results = []
                    for line in _results:
                        if isinstance(line, list):
                            # If the line is a list, we need to join it into a single string
                            line = ' '.join(line)
                        elif not isinstance(line, str):
                            # If it's not a string, we need to convert it to a string
                            line = str(line)
                        results.append({
                            "content": line.strip('["').strip('"]'),
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "engine_used": self.engine
                        })
                    return results

                except json.JSONDecodeError:
                    # The AI returned something that's not valid JSON. We'll treat that as an error
                    logging.error(f"Failed to parse JSON array from AI: {raw_data}. Type: {type(raw_data)}")
                    raise RuntimeError("AI did not return valid JSON array")

            except Exception as e:
                logging.error(f"Attempt {attempt + 1} failed with error: {e}")
                if hasattr(e, 'status_code'):
                    if e.status_code == 429:
                        # Rate-limiting
                        match = RATE_LIMIT_PATTERN.search(e.body['message']) if hasattr(e, 'body') else None
                        if match:
                            delay = float(match.group(1))
                        else:
                            delay = 5
                        sleep_time = delay * BUFFER_MULTIPLIER
                        logging.debug(f"Rate limit reached. Waiting {sleep_time} seconds before retrying...")
                        time.sleep(sleep_time)
                else:
                    _err = e
                    if attempt < max_attempts - 1:
                        backoff_time = 2 ** attempt
                        logging.error(f"Error encountered. Retrying in {backoff_time} seconds...")
                        time.sleep(backoff_time)

        # If we got here, attempts all failed
        if _err is None:
            raise RuntimeError("Failed to get answer from OpenAI API after 3 attempts.")
        else:
            logging.error("Failed to get answer from OpenAI API after 3 attempts.")
            return [{'content': str(_err), 'tokens': 0, 'engine_used': self.engine}]


    def improve_prompt(self, prompt: str, user_id: int):
        _err = None
        for attempt in range(3):
            try:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "- You are an expert OpenAI prompt engineer. You take a string input of the prompt, "
                            "improve it and respond with the new and improved prompt. Do not add anything else.\n"
                            "- Rules: " + pi_settings.prompt + " Respond with the new prompt in a codeblock."
                        )
                    },
                    {
                        "role": "assistant",
                        "content": "Ready to assist with your prompts. Please provide your prompt to improve."
                    }
                ]

                # User's query and payload are appended here
                messages.append(
                    {
                        "role": "user",
                        "content": f"```{prompt}```"
                    }
                )

                completion = self.client.chat.completions.create(
                    model=self.engine,
                    messages=messages,
                    temperature=1,
                    #temperature=self.temperature,
                    #top_p=self.top_p
                )

                data = completion.choices[0].message.content
                tokens_used = completion.usage.total_tokens
                input_tokens = completion.usage.prompt_tokens
                output_tokens = tokens_used - input_tokens

                new_prompt = data.replace("```", "").strip()
                UsersDbCore.add_user_token_usage_pi(user_id, self.engine, tokens_used)
                return {
                    "content": new_prompt,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "engine_used": self.engine
                }

            except json.JSONDecodeError:
                # Handle the case where the response is not a valid JSON string
                raise HTTPException(status_code=500, detail="Failed to parse JSON from assistant response.")
            except Exception as e:
                logging.error(e)
                if getattr(e, 'status_code', None) == 429: # pylint: disable:no-member
                    try:
                        # Use the compiled pattern to search the string
                        message = getattr(e, 'body', {}).get('message', '')
                        match = RATE_LIMIT_PATTERN.search(message) # pylint: disable:no-member
                        # Extract the number of seconds
                        if match:
                            delay = float(match.group(1))
                        else:
                            delay = 5
                    except (ValueError, IndexError):
                        delay = 5  # Default to 5 seconds if parsing fails

                    sleep_time = delay * BUFFER_MULTIPLIER  # Add a buffer time
                    logging.debug(f"Rate limit exceeded. Waiting for {sleep_time} seconds before retrying...")
                    time.sleep(sleep_time)
                else:
                    logging.error(f"OpenAI API error on attempt {attempt + 1}: {e}")
                    _err = e
                    if attempt < 2:
                        # Exponential backoff with a base delay of 1 second
                        time.sleep(1 * (2 ** attempt))

        if _err is None:
            raise RuntimeError("Failed to get answer from OpenAI API after 3 attempts.")
        else:
            logging.error("Failed to get answer from OpenAI API after 3 attempts.")
            logging.error(_err)
            raise HTTPException(status_code=500, detail="Failed to get answer from OpenAI API after 3 attempts.")
