import os
import psycopg2
from psycopg2 import pool, Error
import google.generativeai as genai
from pgvector.psycopg2 import register_vector
import time

# --- Configure Google AI (text-embedding-004) ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
EMBEDDING_MODEL = "models/text-embedding-004"

def get_embedding(text: str) -> list[float]:
    """
    Generates a vector embedding for the given text using Google's text-embedding-004 model.
    Returns the embedding and the latency for the API call.
    """
    if not text:
        return None, 0.0
    try:
        start_api_call = time.time()
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="RETRIEVAL_QUERY"
        )
        end_api_call = time.time()
        return result['embedding'], (end_api_call - start_api_call)
    except Exception as e:
        print(f"Error getting Google embedding for query: {e}")
        return None, 0.0 # Return None for embedding, 0.0 for latency on failure

# --- Database Connection Details ---
DB_HOST = os.getenv("DB_HOST") # Use localhost for proxy connection
DB_PORT = int(os.getenv("DB_PORT")) # Default proxy port for PostgreSQL
DB_NAME = os.getenv("DB_NAME") # Your database name
DB_USER = os.getenv("DB_USER") # Your database user
DB_PASSWORD = os.getenv("DB_PASSWORD") # Your database password


# --- Initialize Global Connection Pool ---
db_pool = None

def initialize_db_pool():
    """
    Initializes the PostgreSQL connection pool using psycopg2.pool.
    This should be called only once at application startup.
    """
    global db_pool
    if db_pool is None:
        try:
            db_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10, # Adjust maxconn based on your application's concurrency needs
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            print("Database connection pool initialized successfully.")
        except Exception as e:
            print(f"Error initializing database connection pool: {e}")
            raise

def close_db_pool():
    """
    Closes all connections in the database pool.
    This should be called when the application is shutting down.
    """
    global db_pool
    if db_pool:
        print("Closing database connection pool...")
        db_pool.closeall()
        db_pool = None
        print("Database connection pool closed.")

# --- Function to perform flexible hybrid search ---
def search_products(query_text: str, filters: dict = None, top_n: int = 5):
    connection = None
    cursor = None
    # Initialize latency variables
    api_call_latency_sec = 0.0
    get_conn_latency_sec = 0.0
    db_query_latency_sec = 0.0
    total_start_time = time.time() # Start total time measurement

    try:
        # --- 1. Construct the full query string (query_text + soft filters) ---
        search_query_text = query_text
        hard_filters_sql = []
        sql_params = []

        soft_filters = {}
        if filters:
            for key, value in filters.items():
                if value is not None:
                    if key in ['min_price', 'max_price']:
                        if key == 'min_price':
                            hard_filters_sql.append("price >= %s")
                            sql_params.append(value)
                        elif key == 'max_price':
                            hard_filters_sql.append("price <= %s")
                            sql_params.append(value)
                    else:
                        soft_filters[key] = value
        
        if soft_filters:
            for key, value in soft_filters.items():
                search_query_text += f" {key} {value}"

        print(f"1. Generating embedding for combined query: '{search_query_text}' using {EMBEDDING_MODEL}...")
        query_embedding, api_call_latency_sec = get_embedding(search_query_text) # Capture API latency

        if query_embedding is None:
            print("   Failed to generate embedding for query. Cannot perform search.")
            return []

        print(f"   Query embedding generated. Dimension: {len(query_embedding)}")

        # --- 2. Get a connection from the pool ---
        if db_pool is None:
            print("   Error: Database pool not initialized. Call initialize_db_pool() first.")
            return []
            
        print("2. Getting connection from pool...")
        start_get_conn = time.time()
        connection = db_pool.getconn()
        end_get_conn = time.time()
        get_conn_latency_sec = end_get_conn - start_get_conn # Store connection retrieval latency
        
        register_vector(connection)
        cursor = connection.cursor()
        print("   Connection retrieved from pool and pgvector adapter registered.")

        # --- 3. Build and Execute the SQL query ---
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

        print(f"3. Executing flexible hybrid search for '{search_query_text}' with hard filters: {hard_filters_sql}...")
        start_db_query = time.time()
        cursor.execute(base_sql, tuple(final_sql_params))
        results = cursor.fetchall()
        end_db_query = time.time()
        db_query_latency_sec = end_db_query - start_db_query # Store DB query execution latency
        print("   Search complete.")

        # --- 4. Print results ---
        print(f"\n--- Top {top_n} Similar Products for '{search_query_text}' (Hard Filters: {filters}) ---")
        if not results:
            print("No similar products found matching the strict price criteria.")
        else:
            for row in results:
                (product_id, product_display_name, brand_name, price, master_category,
                 sub_category, article_type, age_group, gender, base_color, usage,
                 display_categories, article_attributes, description, image_url, cosine_distance) = row
                
                short_description = description[:100] + "..." if len(description) > 100 else description
                
                print(f"ID: {product_id}")
                print(f"  Name: '{product_display_name}'")
                print(f"  Brand: {brand_name}, Price: ${price:.2f}")
                print(f"  Category: {master_category} -> {sub_category} ({article_type})")
                print(f"  Details: {gender}, {age_group}, {base_color}, Usage: {usage}")
                print(f"  Display Cats: {display_categories}")
                print(f"  Article Attrs: {article_attributes}")
                print(f"  Image URL: {image_url}")
                print(f"  Distance: {cosine_distance:.4f}")
                print(f"  Desc: '{short_description}'")
                print("-" * 30)
        
        total_end_time = time.time() # End total time measurement
        total_execution_time = total_end_time - total_start_time

        # --- Consolidated Latency Report ---
        print("\n--- Latency Breakdown ---")
        print(f"API Embedding Call: {api_call_latency_sec:.4f} seconds")
        print(f"DB Connection Retrieval from Pool: {get_conn_latency_sec:.4f} seconds")
        print(f"DB Query Execution: {db_query_latency_sec:.4f} seconds")
        print(f"Total Search Execution Time: {total_execution_time:.4f} seconds")
        print("-------------------------")

        return results

    except (Exception, Error) as e:
        print(f"\nAn error occurred during search: {e}")
        if isinstance(e, psycopg2.OperationalError):
            print("  - Check DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.")
            print("  - Ensure your Cloud SQL instance is running.")
            print("  - Verify 'Authorized Networks' in Cloud SQL allow your Cloud Shell IP.")
        elif isinstance(e, psycopg2.ProgrammingError) and "column" in str(e):
            print("  - Database Programming Error: A column name used in the query might be incorrect or missing.")
            print(f"    Error details: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if connection:
            db_pool.putconn(connection)
            print("4. Database connection returned to pool.")


# --- Main execution block ---
if __name__ == "__main__":
    initialize_db_pool()

    try:
        print("Example 1: Searching for 'red shirt' ")
        search_products(
            query_text="red shirt adults less than 1500",
            filters={
                'max_price': 1500.0
            },
            top_n=5
        )
        print("\n" + "="*80 + "\n")

        print("Example 2: Searching for 'blue jeans' (reusing pool connection)")
        search_products(
            query_text="blue jeans for men",
            filters={
                'gender': 'Men'
            },
            top_n=3
        )
        print("\n" + "="*80 + "\n")

    finally:
        close_db_pool()