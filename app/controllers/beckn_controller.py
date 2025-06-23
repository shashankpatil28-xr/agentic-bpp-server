# app/controllers/beckn_controller.py
from flask import Blueprint, request, jsonify, current_app 
import time # Added for timing
import uuid
import json
from app.services.search_service import SearchService
from app.services.beckn_service import BecknService # Keep this import
from app.utils.async_tasks import run_async_task, run_async_select_task # Import new async task runner
from app.utils.beckn_utils import extract_search_criteria, generate_ack_response, store_pending_request, get_pending_request_results, extract_select_criteria, store_pending_select_request, get_pending_select_request_results # Import new utils

beckn_bp = Blueprint('beckn', __name__)

@beckn_bp.route('/search', methods=['POST'])
def search():
    request_start_time = time.perf_counter()
    data = request.get_json()
    current_app.logger.info(f"Received /search request. Body: {json.dumps(data, indent=2)}")

    context = data.get('context', {})
    message = data.get('message', {})

    transaction_id = context.get('transaction_id', str(uuid.uuid4()))
    message_id = context.get('message_id', str(uuid.uuid4()))
    callback_uri = context.get('bpp_uri') # URI where the on_search response should be sent

    # Transform the callback URI path from '/receiver' to '/caller' for testing purposes
    if callback_uri and '/receiver' in callback_uri:
        original_uri = callback_uri
        callback_uri = original_uri.replace('/receiver', '/caller')
        current_app.logger.info(f"Transformed callback URI from '{original_uri}' to '{callback_uri}'.")

    search_criteria = extract_search_criteria(message)

    current_app.logger.debug(f"Storing pending request for transaction_id: {transaction_id} before ACK.")
    store_pending_request(transaction_id, callback_uri, search_criteria, context)

    ack_response = generate_ack_response(context, "search", transaction_id, message_id)
    current_app.logger.info(f"Generated ACK for transaction_id: {transaction_id}. Preparing to send.")

    # --- IMPORTANT CHANGE HERE ---
    # Pass the actual app instance to the async task function
    run_async_task(current_app._get_current_object(), transaction_id, message_id, search_criteria, context, callback_uri)
    # --- END CHANGE ---

    request_end_time = time.perf_counter()
    current_app.logger.info(f"ACK sent and async search initiated for transaction_id: {transaction_id}. Sync processing time: {(request_end_time - request_start_time) * 1000:.2f} ms.")

    return jsonify(ack_response), 202

@beckn_bp.route('/select', methods=['POST'])
def select():
    request_start_time = time.perf_counter()
    data = request.get_json()
    current_app.logger.info(f"Received /select request. Body: {json.dumps(data, indent=2)}")

    context = data.get('context', {})
    message = data.get('message', {})

    transaction_id = context.get('transaction_id', str(uuid.uuid4()))
    message_id = context.get('message_id', str(uuid.uuid4()))
    callback_uri = context.get('bpp_uri') # URI where the on_select response should be sent

    # Transform the callback URI path from '/receiver' to '/caller' for testing purposes
    if callback_uri and '/receiver' in callback_uri:
        original_uri = callback_uri
        callback_uri = original_uri.replace('/receiver', '/caller')
        current_app.logger.info(f"Transformed callback URI from '{original_uri}' to '{callback_uri}'.")

    select_criteria = extract_select_criteria(message)
    product_id = select_criteria.get('product_id')

    if not product_id:
        current_app.logger.error(f"Invalid /select request: product_id not found in message. Transaction ID: {transaction_id}")
        return jsonify({"error": "Product ID not found in request message."}), 400

    current_app.logger.debug(f"Storing pending select request for transaction_id: {transaction_id} before ACK.")
    store_pending_select_request(transaction_id, callback_uri, product_id, context)

    ack_response = generate_ack_response(context, "select", transaction_id, message_id)
    current_app.logger.info(f"Generated ACK for transaction_id: {transaction_id}. Preparing to send.")

    run_async_select_task(current_app._get_current_object(), transaction_id, message_id, product_id, context, callback_uri)

    request_end_time = time.perf_counter()
    current_app.logger.info(f"ACK sent and async select initiated for transaction_id: {transaction_id}. Sync processing time: {(request_end_time - request_start_time) * 1000:.2f} ms.")

    return jsonify(ack_response), 202

@beckn_bp.route('/on_search', methods=['POST'])
def on_search_received():
    data = request.get_json()
    current_app.logger.info(f"BPP received /on_search (likely from another BPP/BAP for PoC): {json.dumps(data, indent=2)}")
    return jsonify({"message": {"ack": {"status": "ACK"}}}), 200

@beckn_bp.route('/on_select', methods=['POST'])
def on_select_received():
    data = request.get_json()
    current_app.logger.info(f"BPP received /on_select (likely from another BPP/BAP for PoC): {json.dumps(data, indent=2)}")
    return jsonify({"message": {"ack": {"status": "ACK"}}}), 200

@beckn_bp.route('/get_search_results/<transaction_id>', methods=['GET'])
def get_search_results_debug(transaction_id):
    request_start_time = time.perf_counter()
    current_app.logger.info(f"Received /get_search_results request for transaction_id: {transaction_id}")
    results = get_pending_request_results(transaction_id)
    request_end_time = time.perf_counter()
    processing_time_ms = (request_end_time - request_start_time) * 1000

    if results:
        current_app.logger.info(f"Results found for transaction_id: {transaction_id}. Processing time: {processing_time_ms:.2f} ms.")
        return jsonify(results), 200
    
    current_app.logger.warning(f"Results not found or not ready for transaction_id: {transaction_id}. Processing time: {processing_time_ms:.2f} ms.")
    return jsonify({"error": "Results not found or not ready for this transaction_id."}), 404

@beckn_bp.route('/get_select_results/<transaction_id>', methods=['GET'])
def get_select_results_debug(transaction_id):
    request_start_time = time.perf_counter()
    current_app.logger.info(f"Received /get_select_results request for transaction_id: {transaction_id}")
    results = get_pending_select_request_results(transaction_id)
    request_end_time = time.perf_counter()
    processing_time_ms = (request_end_time - request_start_time) * 1000

    if results:
        current_app.logger.info(f"Select results found for transaction_id: {transaction_id}. Processing time: {processing_time_ms:.2f} ms.")
        return jsonify(results), 200
    
    current_app.logger.warning(f"Select results not found or not ready for transaction_id: {transaction_id}. Processing time: {processing_time_ms:.2f} ms.")
    return jsonify({"error": "Select results not found or not ready for this transaction_id."}), 404