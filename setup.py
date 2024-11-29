"""
Setup script for the backend service of EnhancifAI.
Ensures Python 3.10 or newer is used and sets up the package.
"""

import sys
from setuptools import find_packages, setup

# Enforcing Python version requirement
assert sys.version_info[0] == 3 and sys.version_info[1] >= 10, \
    "AI CSV Processor requires Python 3.10 or newer"

setup(
    name='enhancifai_backend',
    version='1.3.1',
    description="EnhancifAI Backend.",
    long_description=open('README.md', 'r', encoding='UTF-8').read(),
    packages=find_packages(exclude=['scripts']),
    install_requires=[
        'openai == 1.0.0',
        'pandas == 2.2.3',
        'fastapi == 0.115.5',
        'uvicorn == 0.32.1',
        'python-multipart',
        'apscheduler',
        'fastapi[security]',
        'google-api-python-client',
        'google-auth-httplib2',
        'google-auth-oauthlib',
        'google-auth',
        'PyJWT == 2.10.1',
        'psycopg2-binary',
        'pydantic[email]',
        'sendgrid == 6.11.0',
        'openpyxl == 3.1.5',
        'gspread == 4.0.0',
        'gspread-dataframe',
        'oauth2client == 4.1.3',
        'google-generativeai',
        'aiofiles == 24.1.0',
        'stripe == 11.3.0',
        'WeasyPrint',
        'requests',
        'httpx == 0.23.0',
    ],
    entry_points={
        'console_scripts': [
            'enhancifai_backend = enhancifai_backend.run_enhancifai:run'
        ]
    }
)
