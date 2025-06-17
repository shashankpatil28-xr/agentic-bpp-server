import re
import math

def parse_ondc_query_string(query_str):
    """
    Parses a comma-separated query string to extract keywords and min/max price.
    This is the core parsing engine.

    Args:
        query_str (str): The query string, e.g.,
                         "t-shirt,black,price > 1000,price < 2000"

    Returns:
        dict: A dictionary containing only keywords, min_price_val, and max_price_val.
    """
    if not query_str:
        return {
            "keywords": [],
            "min_price_val": None,
            "max_price_val": None,
        }

    parts = [part.strip() for part in query_str.split(',') if part.strip()]
    keywords = []

    # Effective range boundaries
    min_val = -math.inf
    max_val = math.inf

    price_pattern = re.compile(r"price\s*([><]=?)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)

    for part in parts:
        match = price_pattern.fullmatch(part)
        if match:
            operator = match.group(1)
            value = float(match.group(2))

            if operator in ('>', '>=') and value > min_val:
                min_val = value
            elif operator in ('<', '<=') and value < max_val:
                max_val = value
        else:
            keywords.append(part)

    final_min_price = min_val if min_val != -math.inf else None
    final_max_price = max_val if max_val != math.inf else None

    # Note: The conflict is still checked internally to avoid invalid ranges,
    # but it is no longer included in the output.
    if final_min_price is not None and final_max_price is not None:
        if final_min_price >= final_max_price:
            # In case of conflict, return no price range.
            final_min_price = None
            final_max_price = None

    # Return the simplified dictionary as requested.
    return {
        "keywords": keywords,
        "min_price_val": final_min_price,
        "max_price_val": final_max_price
    }

def process_search_request(request_body):
    """
    Acts as the entry point for a request. It extracts the query string
    from the request body and passes it to the parser.

    Args:
        request_body (dict): The JSON body of the request.

    Returns:
        dict: The parsed query details in the simplified format.
    """
    try:
        query_str = request_body['message']['intent']['query']
        return parse_ondc_query_string(query_str)
    except (KeyError, TypeError):
        return {
            "error": "Request body must be a valid JSON object with path 'message.intent.query'",
            "keywords": [],
            "min_price_val": None,
            "max_price_val": None,
        }
