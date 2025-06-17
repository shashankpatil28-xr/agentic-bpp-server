# app/services/product_search_service.py
import psycopg2
from psycopg2 import Error
import google.generativeai as genai
import time
from flask import current_app # Import current_app to access Flask config and logger
from app.db.db_pool_manager import get_db_connection, put_db_connection

class ProductSearchService: 
    def __init__(self):
        # Configure Google AI from Flask app config
        google_api_key = current_app.config.get('GOOGLE_API_KEY')
        if not google_api_key:
            current_app.logger.critical("GOOGLE_API_KEY not configured in Flask app config.")
            raise ValueError("GOOGLE_API_KEY not configured in Flask app config.")
        genai.configure(api_key=google_api_key)
        self.EMBEDDING_MODEL = current_app.config.get('EMBEDDING_MODEL', 'models/text-embedding-004')

        # Database connection details are no longer directly used here,
        # but accessed via db_pool_manager, which pulls them from app.config.
        # Basic validation can be removed here as it's done in initialize_db_pool()
        current_app.logger.debug("ProductSearchService initialized.")

    def get_embedding(self, text: str) -> list[float]:
        """
        Generates a vector embedding for the given text using Google's text-embedding-004 model.
        """
        if not text:
            return None
        try:
            embedding_start_time = time.perf_counter()
            result = genai.embed_content(
                model=self.EMBEDDING_MODEL,
                content=text,
                task_type="RETRIEVAL_QUERY"
            )
            embedding_end_time = time.perf_counter()
            current_app.logger.debug(f"Embedding generation latency: {(embedding_end_time - embedding_start_time) * 1000:.2f} ms")
            return result['embedding']
        except Exception as e:
            current_app.logger.error(f"Error getting Google embedding for query: {e}")
            return None

    def search_products(self, query_text: str, filters: dict = None, top_n: int = 5):
        """
        Performs a flexible hybrid search. Price filters remain hard SQL constraints.
        Other categorical/text filters are softened into semantic hints for the embedding.

        Args:
            query_text (str): The natural language query (e.g., "red shirt").
            filters (dict, optional): A dictionary of attributes.
                                      'min_price'/'max_price' are strict SQL filters.
                                      Others (brand, category, color, etc.) are added to query_text.
            top_n (int, optional): The number of top similar products to return. Defaults to 5.
        """
        connection = None
        cursor = None
        search_start_time = time.perf_counter()
        try:
            search_query_text = query_text
            hard_filters_sql = []
            sql_params = []
            
            soft_filters_for_embedding = {}
            hard_filters_for_debug_print = {}

            if filters:
                for key, value in filters.items():
                    if value is not None:
                        if key == 'min_price':
                            hard_filters_sql.append("price >= %s")
                            sql_params.append(value)
                            hard_filters_for_debug_print[key] = value
                        elif key == 'max_price':
                            hard_filters_sql.append("price <= %s")
                            sql_params.append(value)
                            hard_filters_for_debug_print[key] = value
                        else:
                            soft_filters_for_embedding[key] = value
            
            if soft_filters_for_embedding:
                for key, value in soft_filters_for_embedding.items():
                    search_query_text += f" {key}: {value}"

            current_app.logger.info(f"Generating embedding for combined query: '{search_query_text}'...")
            query_embedding = self.get_embedding(search_query_text)

            if query_embedding is None:
                current_app.logger.error("Failed to generate embedding for query. Cannot perform search.")
                return []

            current_app.logger.info(f"Query embedding generated. Dimension: {len(query_embedding)}")

            # --- Get connection from the pool ---
            conn_get_start_time = time.perf_counter()
            connection = get_db_connection() # Use the pool manager function
            conn_get_end_time = time.perf_counter()
            current_app.logger.debug(f"Database connection retrieved from pool: {(conn_get_end_time - conn_get_start_time) * 1000:.2f} ms")

            # register_vector(connection) # No longer needed here, done by get_db_connection()
            cursor = connection.cursor()
            current_app.logger.debug("Connection retrieved from pool.")
            base_sql = f"""
                SELECT
                    product_id,
                    product_display_name,
                    brand_name,
                    price,
                    master_category,
                    sub_category,
                    article_type,
                    age_group,
                    gender,
                    base_color,
                    usage,
                    display_categories,
                    article_attributes,
                    description,
                    image_url,
                    description_embedding <-> %s::vector AS cosine_distance
                FROM
                    products
                WHERE
                    description_embedding IS NOT NULL
                """
        
            final_sql_params = [query_embedding] + sql_params

            if hard_filters_sql:
                base_sql += " AND " + " AND ".join(hard_filters_sql)

            base_sql += """
            ORDER BY
                cosine_distance
            LIMIT %s;
            """
            final_sql_params.append(top_n)

            current_app.logger.info(f"Executing flexible hybrid search for '{search_query_text}' with hard filters: {hard_filters_for_debug_print}...")
            
            query_exec_start_time = time.perf_counter()
            cursor.execute(base_sql, tuple(final_sql_params))
            results = cursor.fetchall()
            query_exec_end_time = time.perf_counter()
            current_app.logger.debug(f"SQL query execution latency: {(query_exec_end_time - query_exec_start_time) * 1000:.2f} ms")
            current_app.logger.info("Search complete.")

            formatted_results = []
            for row in results:
                (product_id, product_display_name, brand_name, price, master_category,
                 sub_category, article_type, age_group, gender, base_color, usage,
                 display_categories, article_attributes, description, image_url, cosine_distance) = row
                
                formatted_results.append({
                    "id": product_id,
                    "name": product_display_name,
                    "description": description,
                    "brand": brand_name,
                    "price": float(price),
                    "currency": "INR",
                    "category": master_category,
                    "sub_category": sub_category,
                    "article_type": article_type,
                    "age_group": age_group,
                    "gender": gender,
                    "color": base_color,
                    "usage": usage,
                    "display_categories": display_categories,
                    "article_attributes": article_attributes,
                    "image_url": image_url,
                    "cosine_distance": cosine_distance
                })
            
            current_app.logger.info(f"Found {len(formatted_results)} products for criteria: {search_query_text}")
            return formatted_results

        except (Exception, Error) as e:
            current_app.logger.critical(f"An error occurred during product search: {e}", exc_info=True)
            if isinstance(e, psycopg2.OperationalError):
                current_app.logger.error("  - Check DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in .env/.config.py.")
                current_app.logger.error("  - Ensure your Cloud SQL instance is running and accessible from the Docker container.")
                current_app.logger.error("  - Verify 'Authorized Networks' in Cloud SQL allow the IP of your Docker host/network.")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                put_db_connection(connection) # Return connection to pool
                current_app.logger.debug("Database connection returned to pool.")
            search_end_time = time.perf_counter()
            current_app.logger.info(f"Overall search function latency: {(search_end_time - search_start_time) * 1000:.2f} ms")