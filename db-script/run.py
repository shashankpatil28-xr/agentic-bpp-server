import os
import psycopg2
from psycopg2 import Error
import google.generativeai as genai
from pgvector.psycopg2 import register_vector
import time # Import the time module

# --- Configure Google AI (text-embedding-004) ---
# IMPORTANT: Load API Key from environment variable for security!
# Replace "AIzaSyDDfqLlEMYIDbdDGy83rCdULQVe3Majte0" with an environment variable lookup
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set. Please set it before running the script.")

genai.configure(api_key=GOOGLE_API_KEY)
EMBEDDING_MODEL = "models/text-embedding-004"

def get_embedding(text: str) -> list[float]:
    """
    Generates a vector embedding for the given text using Google's text-embedding-004 model.
    """
    if not text:
        return None
    try:
        # Measure latency for embedding generation
        embedding_start_time = time.perf_counter()
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="RETRIEVAL_QUERY"
        )
        embedding_end_time = time.perf_counter()
        print(f"   Embedding generation latency: {(embedding_end_time - embedding_start_time) * 1000:.2f} ms")
        return result['embedding']
    except Exception as e:
        print(f"Error getting Google embedding for query: {e}")
        return None

# --- Database Connection Details ---
# IMPORTANT: Load DB credentials from environment variables for security!
DB_HOST = "localhost"  # Change to your actual DB host
# If using Cloud SQL, this should be the Cloud SQL instance connection name
# DB_HOST = os.environ.get('DB_HOST', 'localhost')  # Default to localhost if not set
DB_PORT = 5432  # Default PostgreSQL port
# DB_PORT = os.environ.get('DB_PORT', 5432)  # Default to 5432 if not set
DB_NAME = "postgres"
DB_USER = "product_user"
DB_PASSWORD = "product_password"
# DB_NAME = os.environ.get('DB_NAME', 'postgres')  # Default to postgres if not set


# --- Function to perform flexible hybrid search ---
def search_products(query_text: str, filters: dict = None, top_n: int = 5):
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
    search_start_time = time.perf_counter() # Start overall search timer
    try:
        # --- 1. Construct the full query string (query_text + soft filters) ---
        search_query_text = query_text
        hard_filters_sql = []
        sql_params = [] # Parameters for SQL WHERE clause
        actual_hard_filters_for_print = {} # New dictionary to store only actual hard filters for printing

        # Separate soft filters (for embedding) and hard filters (for SQL WHERE)
        soft_filters = {}
        if filters:
            for key, value in filters.items():
                if value is not None:
                    if key in ['min_price', 'max_price']:
                        # These are hard SQL filters
                        if key == 'min_price':
                            hard_filters_sql.append("price >= %s")
                            sql_params.append(value)
                        elif key == 'max_price':
                            hard_filters_sql.append("price <= %s")
                            sql_params.append(value)
                        actual_hard_filters_for_print[key] = value # Add to print dict
                    else:
                        # These are soft filters, appended to the query text
                        soft_filters[key] = value
        
        # Append soft filters to the query text for semantic understanding
        if soft_filters:
            for key, value in soft_filters.items():
                # Make the appended text natural, e.g., "brand Puma", "color Red"
                search_query_text += f" {key}: {value}"

        print(f"1. Generating embedding for combined query: '{search_query_text}' using {EMBEDDING_MODEL}...")
        query_embedding = get_embedding(search_query_text)

        if query_embedding is None:
            print("   Failed to generate embedding for query. Cannot perform search.")
            return []

        print(f"   Query embedding generated. Dimension: {len(query_embedding)}")

        print(f"2. Connecting directly to database at {DB_HOST}:{DB_PORT}...")
        conn_start_time = time.perf_counter() # Latency for connection
        connection = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn_end_time = time.perf_counter()
        print(f"   Database connection latency: {(conn_end_time - conn_start_time) * 1000:.2f} ms")

        register_vector(connection) # CRUCIAL: Register the pgvector adapter
        cursor = connection.cursor()
        print("   Database connection established and pgvector adapter registered.")

        # --- 3. Build the SQL query ---
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
        
        # Add the query embedding as the first SQL parameter
        final_sql_params = [query_embedding] + sql_params

        # Append hard filters to base SQL
        if hard_filters_sql:
            base_sql += " AND " + " AND ".join(hard_filters_sql)

        base_sql += """
        ORDER BY
            cosine_distance
        LIMIT %s;
        """
        final_sql_params.append(top_n) # Add top_n as the last parameter

        print(f"3. Executing flexible hybrid search for '{search_query_text}' with hard filters: {actual_hard_filters_for_print}...")
        
        query_exec_start_time = time.perf_counter() # Latency for query execution
        cursor.execute(base_sql, tuple(final_sql_params))
        results = cursor.fetchall()
        query_exec_end_time = time.perf_counter()
        print(f"   SQL query execution latency: {(query_exec_end_time - query_exec_start_time) * 1000:.2f} ms")
        print("   Search complete.")

        # --- 4. Print results ---
        # Fixed print statement here to show only actual hard filters
        print(f"\n--- Top {top_n} Similar Products for '{search_query_text}' (Hard Filters Applied: {actual_hard_filters_for_print}, Soft Filters Included: {soft_filters}) ---")
        if not results:
            print("No similar products found matching the strict price criteria.")
            # You could add logic here to suggest widening the price range, etc.
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
            connection.close()
        print("4. Database connection closed.")
        search_end_time = time.perf_counter() # End overall search timer
        print(f"Overall search function latency: {(search_end_time - search_start_time) * 1000:.2f} ms")


# --- Main execution block ---
if __name__ == "__main__":
    # --- IMPORTANT: Set environment variables before running ---
    # export GOOGLE_API_KEY='YOUR_ACTUAL_GOOGLE_API_KEY'
    # export DB_HOST='YOUR_DB_HOST'
    # export DB_PORT='YOUR_DB_PORT'
    # export DB_NAME='YOUR_DB_NAME'
    # export DB_USER='YOUR_DB_USER'
    # export DB_PASSWORD='YOUR_DB_PASSWORD'
    # ---------------------------------------------------------

    print("Example 1: Searching for 'red shirt' with brand 'puma' (soft) and max_price $1500 (hard)")
    search_products(
        query_text="",
        filters={
            'base_color':'red',
            'master_category':'apparel',
            'sub_category':'shirt',  # This is a soft filter
            'brand':'puma',          # This remains a soft filter influencing the embedding
            'max_price': 1500.0      # This is a hard SQL filter
        },
        top_n=5
    )
    print("\n" + "="*80 + "\n")

    print("Example 2: Searching for 'comfortable sportswear' with no filters")
    search_products(query_text="comfortable sportswear", top_n=5)
    print("\n" + "="*80 + "\n")