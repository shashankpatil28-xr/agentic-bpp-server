# app/controllers/beckn_controller.py
from flask import Blueprint, request, jsonify, current_app # <--- current_app is needed here
import uuid
import json
from app.services.search_service import SearchService
from app.services.beckn_service import BecknService
from app.utils.async_tasks import run_async_task 
from app.utils.beckn_utils import extract_search_criteria, generate_ack_response, store_pending_request, get_pending_request_results

beckn_bp = Blueprint('beckn', __name__)

@beckn_bp.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    current_app.logger.info(f"Received /search request: {json.dumps(data, indent=2)}")

    context = data.get('context', {})
    message = data.get('message', {})

    transaction_id = context.get('transaction_id', str(uuid.uuid4()))
    message_id = context.get('message_id', str(uuid.uuid4()))
    bap_uri = context.get('bap_uri')

    search_criteria = extract_search_criteria(message)

    store_pending_request(transaction_id, bap_uri, search_criteria, context)

    ack_response = generate_ack_response(context, "search", transaction_id, message_id)
    current_app.logger.info(f"Sending ACK for transaction_id: {transaction_id}")

    # --- IMPORTANT CHANGE HERE ---
    # Pass the actual app instance to the async task function
    run_async_task(current_app._get_current_object(), transaction_id, message_id, search_criteria, context, bap_uri)
    # --- END CHANGE ---

    return jsonify(ack_response), 202

@beckn_bp.route('/on_search', methods=['POST'])
def on_search_received():
    data = request.get_json()
    current_app.logger.info(f"BPP received /on_search (likely from another BPP/BAP for PoC): {json.dumps(data, indent=2)}")
    return jsonify({"message": {"ack": {"status": "ACK"}}}), 200

@beckn_bp.route('/get_search_results/<transaction_id>', methods=['GET'])
def get_search_results_debug(transaction_id):
    results = get_pending_request_results(transaction_id)
    if results:
        return jsonify(results), 200
    return jsonify({"error": "Results not found or not ready for this transaction_id."}), 404