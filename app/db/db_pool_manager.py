# app/DB/db_pool_manager.py
import psycopg2
from psycopg2 import pool, Error
from pgvector.psycopg2 import register_vector
from flask import current_app # To access Flask config and logger

db_pool = None # Global variable to hold the connection pool

def initialize_db_pool(app):
    """
    Initializes the PostgreSQL connection pool using psycopg2.pool.
    This should be called only once at application startup.
    """
    global db_pool
    if db_pool is None:
        try:
            DB_HOST = app.config.get('DB_HOST')
            DB_PORT = app.config.get('DB_PORT')
            DB_NAME = app.config.get('DB_NAME')
            DB_USER = app.config.get('DB_USER')
            DB_PASSWORD = app.config.get('DB_PASSWORD')

            if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]):
                app.logger.critical("CRITICAL ERROR: Database credentials not fully configured. Cannot initialize DB pool.")
                raise ValueError("Database credentials missing in Flask app config.")

            db_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10, # Adjust maxconn based on your application's concurrency needs
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            app.logger.info("Database connection pool initialized successfully. with host: %s, port: %s, dbname: %s", DB_HOST, DB_PORT, DB_NAME)
        except Exception as e:
            app.logger.critical(f"CRITICAL ERROR: Error initializing database connection pool: {e}", exc_info=True)
            raise # Re-raise the exception to indicate a severe startup failure

def get_db_connection():
    """
    Retrieves a connection from the global database pool.
    """
    global db_pool
    if db_pool is None:
        current_app.logger.error("Attempted to get connection from uninitialized pool.")
        raise Exception("Database connection pool is not initialized. Call initialize_db_pool() first.")
    
    # NEW LOG: Debug log when getting a connection
    current_app.logger.debug("Attempting to get connection from database pool.")
    conn = db_pool.getconn()
    register_vector(conn) 
    current_app.logger.debug("Successfully retrieved connection from database pool.")
    return conn

def put_db_connection(conn):
    """
    Returns a connection to the global database pool.
    """
    global db_pool
    if db_pool:
        # NEW LOG: Debug log when returning a connection
        current_app.logger.debug("Returning connection to database pool.")
        db_pool.putconn(conn)
    else:
        # If pool is already closed/None, just close the connection if it's still open
        if conn and not conn.closed:
            conn.close()
            current_app.logger.debug("Connection returned to pool failed as pool is closed, closing connection directly.")
        else:
            current_app.logger.debug("Attempted to return a connection, but pool was closed or connection already closed.")


def close_db_pool():
    """
    Closes all connections in the database pool.
    This should be called when the application is shutting down.
    """
    global db_pool
    if db_pool:
        current_app.logger.info("Closing database connection pool...")
        db_pool.closeall()
        db_pool = None
        current_app.logger.info("Database connection pool closed.")
    else:
        current_app.logger.debug("close_db_pool called, but pool was already None.")