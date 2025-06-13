# app/services/beckn_service.py
import time
import uuid
import requests
from flask import current_app

class BecknService:
    @staticmethod
    def generate_on_search_response(products, transaction_id, message_id, context):
        bpp_id = current_app.config['BPP_ID']
        bpp_uri = current_app.config['BPP_URI']

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
            "context": {
                "domain": context.get("domain", "e-commerce"),
                "country": context.get("country", "IND"),
                "city": context.get("city", "std:080"),
                "action": "on_search",
                "core_version": context.get("core_version", "1.2.0"),
                "bpp_id": bpp_id,
                "bpp_uri": bpp_uri,
                "transaction_id": transaction_id,
                "message_id": message_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                **context # Merge original context to retain other fields
            },
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
            requests.post(bap_uri + '/beckn/on_search', json=response_payload, timeout=10)
            current_app.logger.info(f"Successfully sent on_search response for transaction {transaction_id} to {bap_uri}")
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Failed to send on_search response for transaction {transaction_id} to {bap_uri}: {e}")