# app/services/beckn_service.py
import time
import uuid
import requests
from urllib.parse import urlparse # Added for audience determination
from flask import current_app
# Import the function from your auth module
from app.auth import make_authenticated_request # Ensure this path is correct

class BecknService:
    @staticmethod
    def generate_on_search_response(products, transaction_id, message_id, context):

        # Start with a copy of the original search request's context.
        # This preserves fields like bap_id, bap_uri, domain, country, city, etc.
        response_context = context.copy()

        # Override fields specific to this BPP and the 'on_search' action.
        response_context['action'] = "on_search"
        response_context['bpp_id'] = context.get('bpp_id')
        response_context['bpp_uri'] = context.get('bpp_uri')
        
        # Ensure the transaction_id from the original request is used.
        # (It's passed as a parameter and should match context['transaction_id'])
        response_context['transaction_id'] = transaction_id
        
        # Set the new message_id for this on_search response.
        response_context['message_id'] = message_id
        
        # Set a new timestamp for this on_search response.
        response_context['timestamp'] = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

        # Handle the version field: output "version" key.
        # Priority: original context's "version" -> original context's "core_version" -> default.
        input_version_val = context.get("version")
        input_core_version_val = context.get("core_version")

        if input_version_val is not None:
            response_context['version'] = input_version_val
        elif input_core_version_val is not None:
            response_context['version'] = input_core_version_val
        else:
            response_context['version'] = "2.0.0" # Default if neither is present

        # Remove 'core_version' key if it was present in the original context and copied,
        # as we are standardizing on the 'version' key in the output.
        if 'core_version' in response_context:
            del response_context['core_version']
            
        # Ensure domain, country, city are present (they would have been copied if in original context).
        # Provide defaults if they were somehow missing from the original context.
        response_context["domain"] = response_context.get("domain", "e-commerce")
        response_context["country"] = response_context.get("country", "IND")
        response_context["city"] = response_context.get("city", "std:080")

        catalog_items = []
        for product in products:
            # Generate image_url as per requirement: gcs/<product_id>.jpg
            # ProductSearchService might return an image_url, but the request specifies to generate it.
            generated_image_url = f"https://storage.mtls.cloud.google.com/retail_images__agenticdemo/images/{product.get('id')}.jpg"

            # Construct the simplified catalog item as per new requirements
            catalog_item = {
                "Item_id": product.get("id"),
                "name": product.get("name"),  # Was previously product.get("name") mapped to descriptor.name
                "images": [generated_image_url], # Was previously under descriptor.images
                "price": {
                    "currency": product.get("currency", "INR"), # price, with default currency
                    "value": str(product.get("price")) 
                },
                "brand_name": product.get("brand") # Directly include brand_name
            }
            catalog_items.append(catalog_item)

        return {
            "context": response_context,
            "message": {
                "catalog": {
                    "bpp/descriptor": {
                        "name": "Your E-commerce BPP",
                        "short_desc": "BPP for seller services"
                    },
                    "bpp/providers": [{
                        "id": "provider1",
                        "descriptor": {
                            "name": "Product Provider Co."
                        },
                        "items": catalog_items
                    }]
                }
            }
        }

    @staticmethod
    def send_on_search_callback(callback_uri: str, response_payload: dict, transaction_id: str):
        if not callback_uri:
            current_app.logger.warning(f"No callback URI provided for transaction {transaction_id}. Cannot send callback.")
            return

        # Determine the target URL for the request and the audience for the token.
        # The `callback_uri` from the Beckn context is typically the base URI of the BAP.
        # The specific action (e.g., /on_search) is appended to this base URI.
        # The `audience` for the ID token is the canonical base URL of the BAP service.

        if not callback_uri.startswith(('http://', 'https://')):
            current_app.logger.error(f"Invalid callback_uri scheme for transaction {transaction_id}: {callback_uri}. Must be http or https.")
            return

        try:
            parsed_bap_uri = urlparse(callback_uri)
            audience_for_token = f"{parsed_bap_uri.scheme}://{parsed_bap_uri.netloc}"
            
            # Construct the full target URL by appending '/on_search'
            # Ensure no double slashes if callback_uri already ends with one.
            target_url_for_request = parsed_bap_uri._replace(path=parsed_bap_uri.path.rstrip('/') + '/on_search').geturl()

        except Exception as e:
            current_app.logger.error(f"Failed to parse callback_uri or construct target URL for transaction {transaction_id}: {callback_uri}. Error: {e}", exc_info=True)
            return

        try:
            current_app.logger.info(f"Attempting to send authenticated on_search for transaction {transaction_id} to {target_url_for_request} with audience {audience_for_token}")

            response = make_authenticated_request(
                url=target_url_for_request, # The full URL to POST to
                method="POST",
                json_payload=response_payload,
                audience=audience_for_token, # The audience for the ID token
                timeout=10
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            current_app.logger.info(f"Successfully sent on_search response for transaction {transaction_id} to {target_url_for_request}. Status: {response.status_code}")
        except ConnectionError as e: # From _get_authenticated_session
            current_app.logger.error(f"Authentication setup failed for callback to {target_url_for_request} (audience: {audience_for_token}): {e}", exc_info=True)
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Failed to send on_search response for transaction {transaction_id} to {target_url_for_request}: {e}", exc_info=True)
        except ValueError as e: # From JSON encoding in make_authenticated_request
            current_app.logger.error(f"Data encoding error for callback to {target_url_for_request}: {e}", exc_info=True)
        except Exception as e: # Catch-all for other unexpected errors
            current_app.logger.error(f"An unexpected error occurred sending on_search to {target_url_for_request}: {e}", exc_info=True)