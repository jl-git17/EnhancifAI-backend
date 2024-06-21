from typing import List
import pandas as pd
import csv
from fastapi import HTTPException

from enhancifai_backend.server.models.execution import PromptObject

class PromptsProcessor:

    @classmethod
    def read_prompt_file(cls, prompt_file_path: str, file_format: str = 'csv'):
        """
        Reads and validates prompts from a CSV or Excel file.
        """
        if file_format not in ['csv', 'excel']:
            raise HTTPException(status_code=400, detail="Invalid file format. Supported formats are 'csv' and 'excel'.")

        def validate_and_parse_float(value, default, min_value=0.0, max_value=2.0):
            """
            Validates and parses a float value ensuring it has exactly one decimal place.
            Falls back to a default value if the input is invalid.
            """
            try:
                num = float(value)
                if min_value <= num <= max_value and len(str(value).split('.')[-1]) == 1:
                    return num
            except ValueError:
                pass
            return default

        valid_prompts = []
        errors = []
        try:
            if file_format == 'csv':
                df = pd.read_csv(prompt_file_path, encoding='utf-8')
            else:  # Excel
                df = pd.read_excel(prompt_file_path, engine='openpyxl')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error reading file: {e}")

        i = 1
        for _, row in df.iterrows():
            try:
                prompt_number = str(row['Line Number'])
                columns = str(row['Columns being Referenced'])
                prompt = str(row['The Prompt'])
                output_heading = str(row['Output Heading'])

                if not prompt_number.isdigit():
                    errors.append(f"Row {i} >> Invalid prompt number: '{prompt_number}'. Prompt number must be a digit.")
                    continue

                columns = columns.replace(" ", "").upper()
                if columns != '*' and not all(c.isalpha() and len(c) == 1 for c in columns.split('+')):
                    if '+' not in columns:
                        errors.append(f"Row {i} >> 'Columns being Referenced' must be separated by a '+' (plus) character. Provided: '{columns}'")
                    else:
                        errors.append(f"Row {i} >> Invalid 'Columns being Referenced' format: '{columns}'. Only single letters or '*' are allowed.")
                    continue

                if not prompt:
                    errors.append(f"Row {i} >> Missing prompt text.")
                    continue

                valid_prompts.append({
                    'prompt_number': prompt_number,
                    'columns': columns,
                    'prompt': prompt,
                    'output_heading': output_heading
                })
                if len(valid_prompts) > 4:
                    errors.append('A maximum of 4 prompts is allowed.')
                    break
                i += 1
            except KeyError as e:
                errors.append(f"Row {i} >> Missing required column: {e}")
                break

        if errors:
            raise HTTPException(status_code=400, detail='\n'.join(errors).strip())

        return valid_prompts

    @classmethod
    def read_prompt_objects(cls, prompts: List[PromptObject]):
        """
        Reads and validates prompts from a list of PromptObject instances.
        """
        valid_prompts = []
        errors = []
        i = 1

        for prompt_obj in prompts:
            try:
                prompt_number = str(i)
                columns = str(prompt_obj.columns)
                prompt = str(prompt_obj.prompt)
                output_heading = str(prompt_obj.output_heading)

                if not prompt_number.isdigit():
                    errors.append(f"Prompt {i} >> Invalid prompt number: '{prompt_number}'. Prompt number must be a digit.")
                    continue

                columns = columns.replace(" ", "").upper()
                if columns != '*' and not all(c.isalpha() and len(c) == 1 for c in columns.split('+')):
                    if '+' not in columns:
                        errors.append(f"Prompt {i} >> 'Columns being Referenced' must be separated by a '+' (plus) character. Provided: '{columns}'")
                    else:
                        errors.append(f"Prompt {i} >> Invalid 'Columns being Referenced' format: '{columns}'. Only single letters or '*' are allowed.")
                    continue

                if not prompt:
                    errors.append(f"Prompt {i} >> Missing prompt text.")
                    continue

                valid_prompts.append({
                    'prompt_number': prompt_number,
                    'columns': columns,
                    'prompt': prompt,
                    'output_heading': output_heading
                })
                if len(valid_prompts) > 4:
                    errors.append('A maximum of 4 prompts is allowed.')
                    break
                i += 1
            except Exception as e:
                errors.append(f"Error processing prompt {i}: {e}")
                break

        if errors:
            raise HTTPException(status_code=400, detail='\n\n'.join(errors).strip())

        return valid_prompts
