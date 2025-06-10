# app/config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your_default_secret_key_semantic_search'
    BPP_ID = os.environ.get('BPP_ID')
    BPP_URI = os.environ.get('BPP_URI')

    # --- Google AI API Key ---
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

    # --- Database Credentials ---
    DB_HOST = os.environ.get('DB_HOST')
    DB_PORT = os.environ.get('DB_PORT', 5432) # Default to 5432 if not set
    DB_NAME = os.environ.get('DB_NAME')
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')

    DEBUG = False
    TESTING = False
    LOG_LEVEL = 'INFO'

class DevelopmentConfig(Config):
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    DEBUG = False
    LOG_LEVEL = 'INFO'

class TestingConfig(Config):
    TESTING = True
    LOG_LEVEL = 'DEBUG'