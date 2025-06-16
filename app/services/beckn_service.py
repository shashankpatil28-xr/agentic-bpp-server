# app/services/beckn_service.py
import time
import uuid
import requests
from flask import current_app

class BecknService:
    @staticmethod
    def generate_on_search_response(products, transaction_id, message_id, context):
        # Get BPP-specific details from app config
        bpp_id_config = current_app.config['BPP_ID']
        bpp_uri_config = current_app.config['BPP_URI']

        # Start with a copy of the original search request's context.
        # This preserves fields like bap_id, bap_uri, domain, country, city, etc.
        response_context = context.copy()

        # Override fields specific to this BPP and the 'on_search' action.
        response_context['action'] = "on_search"
        response_context['bpp_id'] = bpp_id_config
        response_context['bpp_uri'] = bpp_uri_config
        
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
            response_context['version'] = "1.2.0" # Default if neither is present

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

            item_tags = []

            # Brand Name
            if product.get("brand"):
                item_tags.append({"code": "brand_name", "list": [{"code": "value", "value": product.get("brand")}]})
            
            # Article Type
            if product.get("article_type"):
                item_tags.append({"code": "article_type", "list": [{"code": "value", "value": product.get("article_type")}]})

            # Usage
            if product.get("usage"):
                item_tags.append({"code": "usage", "list": [{"code": "value", "value": product.get("usage")}]})
        
            
            # Article Attributes (from jsonb, expected as dict)
            article_attributes = product.get("article_attributes")
            if isinstance(article_attributes, dict):
                for attr_key, attr_value in article_attributes.items():
                    if attr_value is not None: # Ensure value is not None
                        # Sanitize key for "code" (e.g., spaces/hyphens to underscores, lowercase)
                        tag_key_sanitized = f"attr_{attr_key.lower().replace(' ', '_').replace('-', '_')}"
                        item_tags.append({"code": tag_key_sanitized, "list": [{"code": "value", "value": str(attr_value)}]})
            elif article_attributes: # Log if it's not a dict but has a value
                current_app.logger.warning(f"article_attributes for product {product.get('id')} is not a dict: {type(article_attributes)}")


            catalog_item = {

                "descriptor": {
                    "name": product.get("name"),  # product_display_name
                    "long_desc": product.get("description"), # description
                    "images": [generated_image_url] # generated image_url
                },
                "price": {
                    "currency": product.get("currency", "INR"), # price, with default currency
                    "value": str(product.get("price")) 
                },
                "tags": item_tags
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
    def send_on_search_callback(bap_uri, response_payload, transaction_id):
        if not bap_uri:
            current_app.logger.warning(f"No BAP URI provided for transaction {transaction_id}. Cannot send callback.")
            return

        try:
            current_app.logger.info(f"Attempting to send on_search for transaction {transaction_id} to {bap_uri}")
            requests.post(bap_uri + '/on_search', json=response_payload, timeout=10)
            current_app.logger.info(f"Successfully sent on_search response for transaction {transaction_id} to {bap_uri}")
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Failed to send on_search response for transaction {transaction_id} to {bap_uri}: {e}")