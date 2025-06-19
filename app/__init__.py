# app/__init__.py
from flask import Flask
import os
import logging
import atexit
from app.db.db_pool_manager import initialize_db_pool, close_db_pool

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

    # --- Initialize Database Connection Pool ---
    # Call initialize_db_pool here, passing the app instance to access config and logger
    try:
        initialize_db_pool(app)
        atexit.register(close_db_pool, app) # Pass the app instance to the atexit handler
    except Exception as e:
        app.logger.critical(f"Failed to initialize database pool during app startup: {e}")
        # Depending on criticality, you might want to exit here
        # For a web server, a non-functional DB pool means the app is not ready.
        # raise # Uncomment to make startup fail if DB pool init fails

    # --- Register Blueprints ---
    from app.controllers.beckn_controller import beckn_bp
    app.register_blueprint(beckn_bp, url_prefix='/beckn')

    # --- Register app shutdown callback to close the DB pool ---
    # @app.teardown_appcontext
    # def teardown_db_pool(exception=None):
    #     close_db_pool()
    
    app.logger.info("Flask application initialized.")
    return app