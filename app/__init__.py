# app/__init__.py
from flask import Flask
import os
import logging
# import json # NO LONGER NEEDED

# products_data = [] # NO LONGER NEEDED - remove this line

def create_app(config_class=None):
    app = Flask(__name__)

    # --- Configuration Loading ---
    if config_class is None:
        env = os.environ.get('FLASK_ENV', 'development')
        if env == 'production':
            from config import ProductionConfig
            app.config.from_object(ProductionConfig)
        elif env == 'testing':
            from config import TestingConfig
            app.config.from_object(TestingConfig)
        else:
            from config import DevelopmentConfig
            app.config.from_object(DevelopmentConfig)
    else:
        app.config.from_object(config_class)

    # --- Logging Setup ---
    logging.basicConfig(level=app.config.get('LOG_LEVEL', 'INFO'),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    app.logger.info(f"App configured with DEBUG={app.config['DEBUG']} and LOG_LEVEL={app.config['LOG_LEVEL']}")

    # --- REMOVE THIS ENTIRE BLOCK (Dummy Product Data Loading) ---
    # global products_data
    # data_file_path = os.path.join(app.root_path, '..', 'data', 'products.json')
    # try:
    #     with open(data_file_path, 'r') as f:
    #         products_data = json.load(f)
    #     app.logger.info(f"Loaded {len(products_data)} dummy products from {data_file_path}")
    # except FileNotFoundError:
    #     app.logger.critical(f"CRITICAL ERROR: Dummy data file not found at {data_file_path}")
    #     raise
    # except json.JSONDecodeError as e:
    #     app.logger.critical(f"CRITICAL ERROR: Invalid JSON in {data_file_path}: {e}")
    #     raise
    # except Exception as e:
    #     app.logger.critical(f"CRITICAL ERROR: Failed to load dummy product data: {e}")
    #     raise
    # --- END REMOVAL ---


    # --- Register Blueprints ---
    from app.controllers.beckn_controller import beckn_bp
    app.register_blueprint(beckn_bp, url_prefix='/beckn')

    return app