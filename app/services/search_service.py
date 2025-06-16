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
        
        # --- Adapt to the output of beckn_utils.extract_search_criteria ---
        # 'keywords' will be a list of strings.
        # 'min_price_val' and 'max_price_val' will be the price constraints.

        keywords_list = search_criteria.get('keywords', [])
        query_text = " ".join(keywords_list).strip()
        current_app.logger.info(f"Combined query text from keywords: '{query_text}'")

        filters = {}
        min_price = search_criteria.get('min_price_val')
        max_price = search_criteria.get('max_price_val')

        if min_price is not None:
            try:
                filters['min_price'] = float(min_price) # ProductSearchService expects 'min_price'
                current_app.logger.debug(f"Added hard filter: min_price={filters['min_price']}")
            except ValueError:
                current_app.logger.warning(f"Invalid min_price_val: {min_price}. Skipping min_price filter.")
        
        if max_price is not None:
            try:
                filters['max_price'] = float(max_price) # ProductSearchService expects 'max_price'
                current_app.logger.debug(f"Added hard filter: max_price={filters['max_price']}")
            except ValueError:
                current_app.logger.warning(f"Invalid max_price_val: {max_price}. Skipping max_price filter.")

        # Other attributes like color, brand, type are now part of the `query_text`.
        # The ProductSearchService.search_products method's logic for `soft_filters_for_embedding`
        # will not be populated with these from here, which is correct as they are already in `query_text`.

        current_app.logger.info(f"Performing hybrid search with query: '{query_text}', filters: {filters}")
        
        # Call the actual hybrid search function
        products = product_search_service.search_products(
            query_text=query_text,
            filters=filters,
            top_n=10 # You can make this configurable
        )
        return products