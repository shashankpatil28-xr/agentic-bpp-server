# app/services/search_service.py
from flask import current_app
from app.services.product_search_service import ProductSearchService # Import your new service

class SearchService:
    # Initialize the external search service client once per application context
    # This avoids re-initializing genai.configure() and DB credentials on every request
    _product_search_service = None

    @classmethod
    def _get_product_search_service(cls):
        if cls._product_search_service is None:
            # We need an app context to access current_app.config
            with current_app.app_context():
                cls._product_search_service = ProductSearchService()
        return cls._product_search_service

    @staticmethod
    def perform_product_search(search_criteria):
        product_search_service = SearchService._get_product_search_service()
        
        query_text = ""
        filters = {}

        # --- Mapping Beckn Search Criteria to Hybrid Search Inputs ---
        # 1. Extract 'name' as primary query_text
        if 'name' in search_criteria and search_criteria['name']:
            query_text = search_criteria['name']
            current_app.logger.info(f"Extracted primary query text: '{query_text}'")

        # 2. Extract other properties as filters (soft or hard)
        # Assuming Beckn's tags can carry various attributes
        for key, value in search_criteria.items():
            if key == 'name': # Already handled as query_text
                continue
            
            # Example: Price range from Beckn intent (if your BAP sends it)
            # Beckn price range typically comes as a range object, not min/max directly
            # This is an example of how you might map it if your BAP sends it like this:
            # message.intent.payment: { "min_amount": "100", "max_amount": "1000" }
            if key == 'min_price' and value is not None:
                try:
                    filters['min_price'] = float(value)
                    current_app.logger.debug(f"Added hard filter: min_price={filters['min_price']}")
                except ValueError:
                    current_app.logger.warning(f"Invalid min_price value: {value}")
            elif key == 'max_price' and value is not None:
                try:
                    filters['max_price'] = float(value)
                    current_app.logger.debug(f"Added hard filter: max_price={filters['max_price']}")
                except ValueError:
                    current_app.logger.warning(f"Invalid max_price value: {value}")
            
            # Map other Beckn-like attributes to filters for semantic search
            # These will be treated as 'soft' filters by ProductSearchService
            elif key in ['color', 'type', 'brand', 'category', 'master_category', 'sub_category', 'gender', 'age_group']:
                if value is not None:
                    filters[key] = value
                    current_app.logger.debug(f"Added soft filter: {key}={value}")
            # Add more mappings as per your Beckn spec and database columns

        current_app.logger.info(f"Performing hybrid search with query: '{query_text}', filters: {filters}")
        
        # Call the actual hybrid search function
        products = product_search_service.search_products(
            query_text=query_text,
            filters=filters,
            top_n=10 # You can make this configurable
        )
        return products