# Usage Guide for AI CSV Processor

## Getting Started
This guide helps you to use the AI CSV Processor application.

## Running the Application
1. Open the application.
2. Upload your CSV file.
3. Choose the desired processing options.
4. Click 'Process' to start the AI processing on your CSV data.
5. Once processing is complete, download the processed CSV file.

## Features
- **CSV Handling**: Upload and process CSV files with ease.
- **AI Processing**: Leverage AI to analyze and process your data.
- **Easy Download**: Download your processed files with just a click.

## Formatting the Prompt File

To create a prompt file for processing your CSV data, follow the structure as shown in the "Sample Prompts.txt" file:

1. **Sequence Number**: Start with a number indicating the order or sequence of the prompt.
2. **Column Identifier(s)**: After a space-hyphen-space, specify the column(s) from the CSV file that the prompt relates to. Use letters to denote specific columns (e.g., A, B, C) or an asterisk (*) to refer to all columns.
3. **Prompt Instruction**: After a space-hyphen-space, write the actual prompt instruction.
4. **Multiple Columns Note**: Where you specify multiple columns (or all with `*`) make sure to design your prompt such that you specify what to do to which column.

### Example Format

```
1 - G - summarize the complaint text in less than 100 words
2 - G - what is the root cause of the complaint and nothing else
3 - G - list the legal ramifications to the company of not resolving the issue in bullet form. Rank by most severe first
4 - C,D - tell me about the categorization used in all these columns
5 - * - take the value in column A and multiply by the value in column B
```

*Create a text file using this format for each line, defining how your CSV data should be processed.*

