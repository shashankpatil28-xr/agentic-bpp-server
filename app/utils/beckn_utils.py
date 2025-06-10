# app/utils/beckn_utils.py
import time
import uuid
from flask import current_app

_pending_requests = {}

def extract_search_criteria(message):
    search_criteria = {}

    # --- Extract from message.intent.item ---
    if message and 'intent' in message and 'item' in message['intent']:
        item = message['intent']['item']

        # Extract 'name' from descriptor (for query_text)
        if 'descriptor' in item and 'name' in item['descriptor']:
            search_criteria['name'] = item['descriptor']['name']

        # Extract 'category_id' directly from item
        if 'category_id' in item and item['category_id']:
            search_criteria['category'] = item['category_id'] # Mapping to 'category' key for ProductSearchService

        # Extract tags (color, type, etc.) from descriptor
        if 'descriptor' in item and 'tags' in item['descriptor']:
            for tag_group in item['descriptor']['tags']:
                if tag_group.get('code') == 'color' and tag_group.get('list'):
                    for tag_item in tag_group['list']:
                        if tag_item.get('code') == 'name':
                            search_criteria['color'] = tag_item['value']
                            break
                if tag_group.get('code') == 'type' and tag_group.get('list'):
                    for tag_item in tag_group['list']:
                        if tag_item.get('code') == 'name':
                            search_criteria['type'] = tag_item['value']
                            break
                # Add more tag mappings if needed, e.g., 'brand'
                if tag_group.get('code') == 'brand' and tag_group.get('list'):
                    for tag_item in tag_group['list']:
                        if tag_item.get('code') == 'name':
                            search_criteria['brand'] = tag_item['value']
                            break


    # --- Extract from message.intent.payment (for min/max price) ---
    if message and 'intent' in message and 'payment' in message['intent']:
        payment = message['intent']['payment']
        
        if 'min_amount' in payment and payment['min_amount'] is not None:
            try:
                search_criteria['min_price'] = float(payment['min_amount'])
            except ValueError:
                current_app.logger.warning(f"Invalid min_amount value: {payment['min_amount']}. Skipping price filter.")
        
        if 'max_amount' in payment and payment['max_amount'] is not None:
            try:
                search_criteria['max_price'] = float(payment['max_amount'])
            except ValueError:
                current_app.logger.warning(f"Invalid max_amount value: {payment['max_amount']}. Skipping price filter.")
                
    current_app.logger.info(f"Extracted search criteria: {search_criteria}")
    return search_criteria

def generate_ack_response(original_context, action, transaction_id, message_id):
    return {
        "context": {
            "domain": original_context.get("domain", "e-commerce"),
            "country": original_context.get("country", "IND"),
            "city": original_context.get("city", "std:080"),
            "action": action,
            "core_version": original_context.get("core_version", "1.2.0"),
            "bpp_id": current_app.config['BPP_ID'],
            "bpp_uri": current_app.config['BPP_URI'],
            "transaction_id": transaction_id,
            "message_id": message_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        },
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