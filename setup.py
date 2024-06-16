"""
Setup script for the AI CSV Processor.
Ensures Python 3.10 or newer is used and sets up the package.
"""

import sys
from setuptools import find_packages, setup

# Enforcing Python version requirement
assert sys.version_info[0] == 3 and sys.version_info[1] >= 10, \
    "AI CSV Processor requires Python 3.10 or newer"

# TODO: freeze packages

setup(
    name='enhancifai_backend',
    version='0.1.0',
    description="EnhancifAI Backend.",
    long_description=open('README.md', 'r', encoding='UTF-8').read(),
    packages=find_packages(exclude=['scripts']),
    install_requires=[
        'openai',
        'pandas',
        'fastapi',
        'uvicorn',
        'python-multipart',
        'apscheduler',
        'fastapi[security]',
        'google-api-python-client',
        'google-auth-httplib2',
        'google-auth-oauthlib',
        'PyJWT',
        'psycopg2-binary',
        'pydantic[email]',
        'sendgrid',
        'openpyxl',
        'gspread',
        'oauth2client',
        'google-generativeai',
        'aiofiles'
    ],
    entry_points={
        'console_scripts': [
            'enhancifai_backend = enhancifai_backend.run_enhancifai:run'
        ]
    }
)
