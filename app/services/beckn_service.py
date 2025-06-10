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
            catalog_items.append({
                "id": product.get("id"),
                "descriptor": {
                    "name": product.get("name"),
                    "description": product.get("description")
                },
                "price": {
                    "currency": product.get("currency"),
                    "value": str(product.get("price"))
                },
                "category_id": product.get("category"),
                "fulfillment_id": "fulfillment1", # Example, usually comes from provider
                "tags": [ # Example tags, can be more detailed
                    {"code": "color", "list": [{"code": "name", "value": product.get("color")}]},
                    {"code": "type", "list": [{"code": "name", "value": product.get("type")}]}
                ]
            })

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
                    "bpp/fulfillments": [{
                        "id": "fulfillment1",
                        "type": "Delivery"
                    }],
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