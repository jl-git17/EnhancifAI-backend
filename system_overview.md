# System Overview

## Non-Technical Overview

EnhancifAI Backend is a Python-based service designed to process CSV and Excel files using advanced AI algorithms. It integrates with OpenAI and Gemini models to provide AI-powered data processing capabilities. The system also includes features for billing, user management, and Google Sheets integration. An admin dashboard is available for managing settings, logs, and billing operations.

### Key Features
- **AI-Powered Processing**: Leverages OpenAI and Gemini models for advanced data analysis.
- **CSV and Excel Support**: Handles file uploads and processing for these formats.
- **Prompt Improver**: Enhances user-provided prompts for better AI interactions.
- **Billing Integration**: Includes Stripe integration for managing subscriptions and payments.
- **Google Sheets Integration**: Supports importing/exporting data to Google Sheets.
- **Admin Dashboard**: Provides an interface for managing system settings, logs, and billing.

## Technical Overview

### Architecture
The system is built using the FastAPI framework and follows a modular architecture. Key components include:

1. **AI Module**: Handles interactions with OpenAI and Gemini APIs for AI-powered tasks.
2. **Database Module**: Manages database access and operations using PostgreSQL.
3. **Engine Module**: Implements core processing logic for handling CSV/Excel files and managing prompts.
4. **Integrations Module**: Includes external service integrations like Stripe and SendGrid.
5. **Server Module**: Implements the FastAPI server, including routes, models, and static files for the admin dashboard.

### Key Components

#### AI Module
- **openai_api.py**: Manages interactions with OpenAI APIs, including prompt improvement and data analysis.
- **gemini.py**: Handles Gemini model-specific operations, providing an alternative AI engine for specific tasks.

#### Database Module
- **core.py**: Provides database session management, including connection pooling and query execution.
- **handlers/**: Contains handlers for various entities like users, runs, billing, and Google Sheets integration. Examples include:
  - **users.py**: Manages user-related database operations.
  - **billing.py**: Handles billing-related database queries.
  - **runs.py**: Tracks and manages AI processing runs.

#### Engine Module
- **csv_handler.py**: Processes CSV files, including validation and transformation.
- **excel_handler.py**: Processes Excel files, supporting multiple sheets and formats.
- **prompts.py**: Manages prompt-related operations, including validation and optimization.
- **rate_limit_manager.py**: Implements rate-limiting logic to ensure compliance with API usage limits.

#### Integrations Module
- **monthly_billing.py**: Automates billing tasks, including invoice generation and payment processing.
- **sendgrid_api.py**: Manages email notifications using the SendGrid API.

#### Server Module
- **serve.py**: Configures and runs the FastAPI server, including middleware and route registration.
- **routes/**: Defines API endpoints for various functionalities, such as user management, billing, and file uploads.
- **pages/**: Contains HTML templates for the admin dashboard, including pages for billing, logs, and prompt management.

### Configuration
The system uses environment variables for configuration, managed via the `config.py` file. Key settings include:
- **Database Configuration**: Host, name, username, password, and schema.
- **API Keys**: OpenAI, SendGrid, and Stripe API keys.
- **Server Settings**: Host and port for the FastAPI server.
- **Admin Credentials**: Username and password for accessing admin routes.

### Deployment
The application can be deployed using Docker. A `Dockerfile` is included for containerization, and the system supports running in a production environment with minimal setup. Key steps include:
1. Building the Docker image using `docker build`.
2. Running the container with appropriate environment variables.
3. Configuring a reverse proxy (e.g., Nginx) for HTTPS and load balancing.

### Scheduler
The system uses APScheduler for background tasks, such as:
- **Database Maintenance**: Keeping the database connection alive.
- **File Cleanup**: Deleting old files to free up storage.
- **Billing Automation**: Generating and charging invoices.
- **Rate Limit Management**: Cleaning up expired rate limit entries.

### Security
- **Authentication**: Uses JWT for secure API access, ensuring that only authorized users can interact with the system.
- **Authorization**: Admin routes are protected with HTTP Basic Authentication, requiring valid credentials.
- **Data Encryption**: Sensitive data, such as API keys and passwords, is stored securely using environment variables.

### Future Enhancements
- **Improved AI Model Support**: Adding support for additional AI models and fine-tuning existing ones.
- **Enhanced Logging and Monitoring**: Implementing centralized logging and real-time monitoring for better observability.
- **Additional Integrations**: Expanding support for third-party services, such as payment gateways and cloud storage providers.
- **Scalability Improvements**: Optimizing the system for horizontal scaling to handle increased traffic and data volume.