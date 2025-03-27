# EnhancifAI Backend

## Overview
EnhancifAI Backend is a Python-based service designed for processing CSV and Excel files using AI algorithms. It integrates functionalities for handling CSV and Excel files, as well as interacting with OpenAI's API.

## Features
- **AI-Powered Processing**: Leverages OpenAI and Gemini models for advanced data processing.
- **CSV and Excel Support**: Handles CSV and Excel files for input and output.
- **Prompt Improver**: Enhances user-provided prompts for better AI interactions.
- **Billing and User Management**: Includes billing integration with Stripe and user management features.
- **Google Sheets Integration**: Supports importing and exporting data to Google Sheets.
- **Admin Dashboard**: Provides an admin interface for managing settings, logs, and billing.

## Project Structure
- `ai/`: Contains AI-related modules, including OpenAI and Gemini integrations.
- `database/`: Manages database access, schema, and handlers for various entities like users, runs, and billing.
- `engine/`: Implements core processing logic for handling CSV/Excel files and managing prompts.
- `integrations/`: Includes external service integrations like Stripe and SendGrid.
- `oauth/`: Handles OAuth authentication, particularly for Google services.
- `server/`: Implements the FastAPI server, including routes, models, and static files for the admin dashboard.
- `Usage.md`: Provides a detailed guide on using the application.

## Getting Started
1. Clone the repository.
2. Install dependencies using `pip install -r requirements.txt`.
3. Set up environment variables as specified in `.env`.
4. Run the application using `python enhancifai_backend/run_enhancifai.py`.

## Usage
Refer to the [Usage Guide](Usage.md) for detailed instructions on how to use the application, including formatting prompt files and processing data.

## Contributing
Contributions are welcome! Please fork the repository and submit a pull request for review.

## License
This project is licensed under the MIT License.

