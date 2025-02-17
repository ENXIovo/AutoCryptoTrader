"""
Configuration settings for the application.

This module contains various configuration settings used by the application, including:
- Deployment configurations for different OpenAI models.
- OpenAI API versioning.
- Endpoint configurations for different regions.
- Chat session settings.
- Redis and MySQL database connection details.

The configurations are primarily sourced from environment variables, ensuring that sensitive
information and settings can be managed securely and flexibly.

Configuration Details:
----------------------
1. **Deployment Configuration**:
   - `DEFAULT_DEPLOYMENT_NAME` (str): Default deployment model name for the OpenAI API.
     Example: "gpt-4-turbo-2024-04-09"

2. **OpenAI API Configuration**:
   - `OPENAI_API_VERSION` (str): API version for the OpenAI services.
     Example: "2024-02-01"

3. **Endpoint Configurations**:
   - `ENDPOINT_CONFIGS` (dict): Dictionary containing API keys, endpoints, and available models
     for different regions.
     - **Keys**:
       - `"EASTUS"`: Configuration for the East US region.
       - `"EASTUS2"`: Configuration for the East US 2 region.
       - `"FRANCECENTRAL"`: Configuration for the France Central region.
     - **Values**:
       - `"api_key"` (str): API key for the respective region.
       - `"endpoint"` (str): Endpoint URL for the respective region.
       - `"models"` (list of str): List of available models for the respective region.

4. **Chat Session Configuration**:
   - `DEFAULT_SYSTEM_MESSAGE` (str): Default system message for the assistant.
     Example: "You are a helpful assistant."
   - `DEFAULT_CONTEXT_LENGTH` (int): Default context length for chat sessions.
     Example: 12
   - `DEFAULT_TEMPERATURE` (float): Default temperature setting for response generation.
     Example: 0.7

5. **Input Fields Configuration**:
   - `DEFAULT_INPUT_FIELDS` (set): Default input fields for handling messages.
     Example: {"role", "content"}

6. **Redis Configuration**:
   - `REDIS_HOST` (str): Redis server hostname.
   - `REDIS_PORT` (int): Redis server port.
   - `REDIS_DB` (int): Redis database number.
   - `REDIS_PASSWORD` (str): Redis server password.

7. **MySQL Configuration**:
   - `MYSQL_USERNAME` (str): MySQL database username.
   - `MYSQL_PASSWORD` (str): MySQL database password.
   - `MYSQL_HOST` (str): MySQL database hostname.
   - `MYSQL_PORT` (int): MySQL database port.
   - `MYSQL_DB` (str): MySQL database name.
   - `DATABASE_URL` (str): SQLAlchemy connection URL for the MySQL database.

Example:
--------
To use these configurations, ensure that the necessary environment variables are set.
You can create a `.env` file or set these variables in your environment directly.

Environment Variables:
----------------------
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_GPT4_KEY`
- `AZURE_OPENAI_GPT4_ENDPOINT`
- `AZURE_OPENAI_FC_KEY`
- `AZURE_OPENAI_FC_ENDPOINT`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_DB`
- `REDIS_PASSWORD`
- `MYSQL_USERNAME`
- `MYSQL_PASSWORD`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_DB`
"""

import os

# Deployment Configuration
# Options:
# "gpt-35-turbo"
# "gpt-35-turbo-16k"
# "gpt-35-turbo-1106"
# "gpt-4-0613"
# "gpt-4-1106-Preview"
# "gpt-4-0125-Preview"
# "gpt-4-turbo-2024-04-09"
# "gpt-4o-2024-05-13"
DEFAULT_DEPLOYMENT_NAME = "gpt-4o-2024-11-20"

# OpenAI API Configuration
OPENAI_API_VERSION = "2024-02-01"

ENDPOINT_CONFIGS = {
    "OPENAI": {
        "api_key": os.getenv("OPENAI_API_KEY"),
        "models": ["gpt-4o-2024-11-20"],
    }
}

# Chat Session Configuration
DEFAULT_SYSTEM_MESSAGE = "You are a helpful assistant."
DEFAULT_CONTEXT_LENGTH = 12
DEFAULT_TEMPERATURE = 0.7

# Input Fields Configuration
DEFAULT_INPUT_FIELDS = {"role", "content"}

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
REDIS_DB = int(os.getenv("REDIS_DB"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
