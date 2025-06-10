# app/utils/async_tasks.py
import threading
# from flask import current_app # No longer needed here
from app.services.search_service import SearchService
from app.services.beckn_service import BecknService
from app.utils.beckn_utils import update_pending_request_with_result

# --- IMPORTANT CHANGE HERE ---
# The function now accepts the 'app_instance'
def _perform_search_and_callback(app_instance, transaction_id, message_id, search_criteria, context, bap_uri):
    # Use the passed app_instance to push the context
    with app_instance.app_context():
        try:
            app_instance.logger.info(f"Async task: Starting search for transaction_id: {transaction_id}")
            products = SearchService.perform_product_search(search_criteria)
            beckn_response = BecknService.generate_on_search_response(products, transaction_id, message_id, context)

            update_pending_request_with_result(transaction_id, beckn_response)

            BecknService.send_on_search_callback(bap_uri, beckn_response, transaction_id)

            app_instance.logger.info(f"Async task: Completed for transaction_id: {transaction_id}")
        except Exception as e:
            app_instance.logger.error(f"Async task: Error during search for transaction_id {transaction_id}: {e}")

# The run_async_task also needs to accept 'app_instance'
def run_async_task(app_instance, transaction_id, message_id, search_criteria, context, bap_uri):
    thread = threading.Thread(target=_perform_search_and_callback,
                              args=(app_instance, transaction_id, message_id, search_criteria, context, bap_uri))
    thread.start()
    app_instance.logger.info(f"Async task for transaction {transaction_id} started in background.")
# --- END CHANGE ---