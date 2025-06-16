# app/utils/beckn_utils.py
import time
import uuid
from flask import current_app
from app.services.parse_query_string import parse_ondc_query_string # Import the new parser

_pending_requests = {}

def extract_search_criteria(message):
    # Initialize with keys expected by the (potentially updated) SearchService
    search_criteria = {
        "keywords": [],
        "min_price_val": None,
        "max_price_val": None
    }

    if not message or 'intent' not in message:
        current_app.logger.warning("No 'intent' found in message. Cannot extract search criteria.")
        return search_criteria

    intent = message['intent']

    # --- New: Prioritize message.intent.query if present ---
    if 'query' in intent and isinstance(intent['query'], str) and intent['query'].strip():
        query_str = intent['query']
        # Note: query_str should contain literal '>' and '<', not HTML entities like '&gt;'.
        current_app.logger.info(f"Found 'message.intent.query': \"{query_str}\". Using new parser.")
        
        parsed_query = parse_ondc_query_string(query_str)
        
        search_criteria['keywords'] = parsed_query.get('keywords', [])
        if parsed_query.get('min_price_val') is not None:
            search_criteria['min_price_val'] = parsed_query['min_price_val']
        if parsed_query.get('max_price_val') is not None:
            search_criteria['max_price_val'] = parsed_query['max_price_val']
        
        # If query string provides price, we might decide to ignore payment block for price.
        # For now, the payment block below will only fill prices if they are still None.

    # --- Fallback: Extract from message.intent.item (old structured way) ---
    # This block executes if 'query' was not present or was empty.
    elif 'item' in intent:
        current_app.logger.info("No 'message.intent.query' found or it was empty. Attempting to extract from 'message.intent.item'.")
        item = intent['item']

        # Extract 'name' from descriptor (add to keywords)
        if 'descriptor' in item and 'name' in item['descriptor'] and item['descriptor']['name']:
            search_criteria['keywords'].append(item['descriptor']['name'])

        # Extract 'category_id' (add to keywords)
        if 'category_id' in item and item['category_id']:
            search_criteria['keywords'].append(item['category_id'])

        # Extract tags (color, type, brand etc. add to keywords)
        if 'descriptor' in item and 'tags' in item['descriptor']:
            for tag_group in item['descriptor']['tags']:
                if tag_group.get('list'):
                    # Example: if tag_group.get('code') is 'color', 'brand', 'type'
                    # and tag_item.get('code') is 'name'
                    for tag_item in tag_group['list']:
                        if tag_item.get('code') == 'name' and tag_item.get('value'):
                            search_criteria['keywords'].append(tag_item['value'])
                            # Original code had a break here, implying one value per tag group.
                            # If multiple values are possible (e.g. list of colors), remove break.
                            # For simplicity, keeping it to one value per distinct tag group code for now.
                            break 

    # --- Payment details: Apply if not already set by the query string parser, or augment ---
    if 'payment' in intent:
        payment = intent['payment']
        
        # Only set from payment if not already set (e.g., by query string)
        if search_criteria.get('min_price_val') is None and \
           'min_amount' in payment and payment['min_amount'] is not None:
            try:
                search_criteria['min_price_val'] = float(payment['min_amount'])
            except ValueError:
                current_app.logger.warning(f"Invalid min_amount value: {payment['min_amount']}. Skipping price filter.")
        
        if search_criteria.get('max_price_val') is None and \
           'max_amount' in payment and payment['max_amount'] is not None:
            try:
                search_criteria['max_price_val'] = float(payment['max_amount'])
            except ValueError:
                current_app.logger.warning(f"Invalid max_amount value: {payment['max_amount']}. Skipping price filter.")
                
    current_app.logger.info(f"Extracted search criteria: {search_criteria}")
    return search_criteria

def generate_ack_response(original_context, action, transaction_id, message_id):
    # Start with a copy of the original context to preserve fields like domain, country, city, bap_id, bap_uri etc.
    response_context = original_context.copy()

    # Override fields specific to this BPP and the ACK action.
    response_context['action'] = action # The action for this response (e.g., "on_search")
    response_context['bpp_id'] = current_app.config['BPP_ID']
    response_context['bpp_uri'] = current_app.config['BPP_URI']
    
    # Ensure the transaction_id from the original request is used.
    response_context['transaction_id'] = transaction_id # Should be same as original_context's
    
    # Set the new message_id for this ACK response.
    response_context['message_id'] = message_id 
    
    # Set a new timestamp for this ACK response.
    response_context['timestamp'] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    # Handle the version field: output "version" key.
    # Priority: original context's "version" -> original context's "core_version" -> default.
    input_version_val = original_context.get("version")
    input_core_version_val = original_context.get("core_version")

    if input_version_val is not None:
        response_context['version'] = input_version_val
    elif input_core_version_val is not None:
        response_context['version'] = input_core_version_val
    else:
        response_context['version'] = "1.2.0" # Default if neither is present

    # Remove 'core_version' key if it was present in the original context and copied.
    if 'core_version' in response_context:
        del response_context['core_version']

    return {
        "context": response_context,
        "message": {
            "ack": {
                "status": "ACK"
            }
        }
    }

def store_pending_request(transaction_id, bap_uri, search_criteria, context):
    _pending_requests[transaction_id] = {
        "bap_uri": bap_uri,
        "search_criteria": search_criteria,
        "context": context,
        "status": "pending",
        "timestamp": time.time(),
        "beckn_response": None
    }

def get_pending_request_results(transaction_id):
    request_data = _pending_requests.get(transaction_id)
    if request_data and request_data.get("beckn_response"):
        del _pending_requests[transaction_id] # Clean up after retrieval
        return request_data["beckn_response"]
    return None

def update_pending_request_with_result(transaction_id, beckn_response):
    if transaction_id in _pending_requests:
        _pending_requests[transaction_id]["beckn_response"] = beckn_response
        _pending_requests[transaction_id]["status"] = "completed"

def get_pending_request_details(transaction_id):
    return _pending_requests.get(transaction_id)