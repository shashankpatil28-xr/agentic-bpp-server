# app/utils/async_tasks.py
import threading
# from flask import current_app # No longer needed here
from app.services.search_service import SearchService
from app.services.beckn_service import BecknService
from app.utils.beckn_utils import update_pending_request_with_result, update_pending_select_request_with_result

# --- IMPORTANT CHANGE HERE ---
# The function now accepts the 'app_instance'
def _perform_search_and_callback(app_instance, transaction_id, message_id, search_criteria, context, callback_uri):
    # Use the passed app_instance to push the context
    with app_instance.app_context():
        try:
            app_instance.logger.info(f"Async task: Starting search for transaction_id: {transaction_id}")
            products = SearchService.perform_product_search(search_criteria)
            beckn_response = BecknService.generate_on_search_response(products, transaction_id, message_id, context)

            update_pending_request_with_result(transaction_id, beckn_response)

            BecknService.send_on_search_callback(callback_uri, beckn_response, transaction_id)

            app_instance.logger.info(f"Async task: Completed for transaction_id: {transaction_id}")
        except Exception as e:
            app_instance.logger.error(f"Async task: Error during search for transaction_id {transaction_id}: {e}")

# The run_async_task also needs to accept 'app_instance'
def run_async_task(app_instance, transaction_id, message_id, search_criteria, context, callback_uri):
    thread = threading.Thread(target=_perform_search_and_callback,
                              args=(app_instance, transaction_id, message_id, search_criteria, context, callback_uri))
    thread.start()
    app_instance.logger.info(f"Async search task for transaction {transaction_id} started in background.")

def _perform_select_and_callback(app_instance, transaction_id, message_id, product_id, context, callback_uri):
    """
    Background task to perform product selection and send the on_select callback.
    """
    with app_instance.app_context():
        try:
            app_instance.logger.info(f"Async select task: Starting select for transaction_id: {transaction_id}, product_id: {product_id}")
            product_details = SearchService.perform_product_select(product_id)

            if not product_details:
                app_instance.logger.error(f"Async select task: Product with ID {product_id} not found. Cannot generate on_select. Transaction ID: {transaction_id}")
                return

            beckn_response = BecknService.generate_on_select_response(product_details, transaction_id, message_id, context)

            update_pending_select_request_with_result(transaction_id, beckn_response)

            BecknService.send_on_select_callback(callback_uri, beckn_response, transaction_id)
            app_instance.logger.info(f"Async select task: Completed for transaction_id: {transaction_id}")
        except Exception as e:
            app_instance.logger.error(f"Async select task: Error during select for transaction_id {transaction_id}: {e}", exc_info=True)

def run_async_select_task(app_instance, transaction_id, message_id, product_id, context, callback_uri):
    thread = threading.Thread(target=_perform_select_and_callback, args=(app_instance, transaction_id, message_id, product_id, context, callback_uri))
    thread.start()
    app_instance.logger.info(f"Async select task for transaction {transaction_id} started in background.")
# --- END CHANGE ---