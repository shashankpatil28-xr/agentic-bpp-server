import logging
import requests
from urllib.parse import urlparse, urlunparse
from io import BytesIO
import json # Import json for handling JSON payloads
# Google Cloud authentication libraries
from google.auth import default
from google.auth.transport.requests import AuthorizedSession
import google.oauth2.id_token # Import for fetching ID tokens
from cachetools import TTLCache # For caching ID tokens
import google.auth.transport.requests as google_auth_requests # For the request object for fetch_id_token

# Assuming 'your/package/log' maps to Python's standard logging
logger = logging.getLogger(__name__)

# The _get_authenticated_session function and _authenticated_sessions_cache
# were based on a misunderstanding of AuthorizedSession for ID tokens.
# ID tokens should be fetched per request or cached with their expiry.
# We will fetch the ID token directly in make_authenticated_request.

# Cache for Google ID tokens. Tokens are valid for 1 hour. We'll cache them for 55 minutes (3300 seconds)
# to ensure we don't use an expired token.
id_token_cache = TTLCache(maxsize=100, ttl=3300)
# We will fetch the ID token directly in make_authenticated_request.


# Mimicking func proxy(ctx *model.StepContext, r *http.Request, w http.ResponseWriter, target *url.URL)
# For 'r' and 'w', we assume standard Python WSGI/HTTP server request/response objects
# For 'target', we assume a urllib.parse.ParseResult object or a string that can be parsed.
def proxy(request_obj, response_writer, target_url_str: str):
    """
    Proxies an incoming HTTP request to a target URL with Google ID Token authentication.

    Args:
        request_obj: The incoming HTTP request object (e.g., Flask's request, or a raw WSGI env).
                     It must have access to method, headers, URL, and body.
        response_writer: The HTTP response writer object.
        target_url_str: The string representation of the target URL.
    """
    # This function is designed for handling *incoming* web requests to the proxy.
    # It is not the correct function to use for making *outgoing* authenticated calls
    # from your server's internal logic (like an on_search callback).
    # Please use the `make_authenticated_request` function below for that purpose.
    logger.error("The 'proxy' function is not intended for making outgoing service calls. Use 'make_authenticated_request' instead.")
    # You might want to return an error or raise an exception here if this function is called unexpectedly
    # For now, let's just indicate it's not the right usage.
    if response_writer:
         response_writer.status = "501 Not Implemented"
         response_writer.write(b"This endpoint is not configured as a general proxy for outgoing calls.")
    # In a real scenario, you'd likely remove or refactor this function entirely
    # if its only purpose was the outgoing call scenario.
    pass

def make_authenticated_request(
    url: str,
    method: str,
    headers: dict = None,
    data: bytes = None,
    json_payload: dict = None,
    audience: str = None, # The audience for the ID token
    bearer_token: str = None, # Allows providing a pre-existing bearer token
    timeout: int = 10
) -> requests.Response:
    """
    Makes an authenticated HTTP request to a target URL with Google ID Token authentication.

    Args:
        url: The target URL string.
        method: The HTTP method (e.g., 'GET', 'POST').
        headers: Optional dictionary of headers.
        data: Optional request body (bytes or str).
        json_payload: Optional dictionary for JSON payload (will be converted to data).
                      If both data and json_payload are provided, data takes precedence.
        audience: The audience for the Google ID Token. Required for Cloud Run/Functions auth.
                  This is ignored if `bearer_token` is provided.
                  If None, authentication will not be applied (useful for testing public endpoints).
        timeout: Request timeout in seconds.

    Returns:
        The requests.Response object.

    Raises:
        ConnectionError: If authentication setup fails.
        requests.exceptions.RequestException: If the HTTP request fails.
        ValueError: If JSON encoding fails.
    """
    # Use a standard requests session. Authentication will be handled by adding an ID token if audience is provided.
    session = requests.Session()
    auth_header_value = None # Will hold the "Bearer <token>" string
    
    # Prepare headers - copy provided headers and ensure Authorization is handled by AuthorizedSession
    outgoing_headers = {}
    if headers:
        for name, value in headers.items():
             # AuthorizedSession handles the Authorization header
            if name.lower() != 'authorization':
                outgoing_headers[name] = value

    if bearer_token:
        auth_header_value = f'Bearer {bearer_token}'
        logger.info(f"Using provided bearer token for authentication to {url}.")
    elif audience:
        # --- Check for a cached token first ---
        fetched_id_token = id_token_cache.get(audience)
        if fetched_id_token:
            logger.info(f"Using cached ID token for audience: {audience}")
        else:
            logger.info(f"No cached token for audience: {audience}. Fetching a new one.")
            try:
                # Obtain credentials using Application Default Credentials.
                credentials, project = default()
                auth_req = google_auth_requests.Request() # Create a transport request object
                
                # Fetch the ID token for the specified audience.
                fetched_id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)
                logger.debug(f"DEBUG: Fetched ID token (truncated): {fetched_id_token[:20]}... for audience: {audience}")
                
                # Store the newly fetched token in the cache
                id_token_cache[audience] = fetched_id_token
                logger.info(f"Successfully fetched and cached new ID token for audience: {audience}")
            except Exception as e:
                logger.error(f"Failed to fetch ID token for audience {audience}: {e}", exc_info=True)
                raise ConnectionError(f"Authentication setup failed: Could not get ID token for audience {audience}.") from e
        
        auth_header_value = f'Bearer {fetched_id_token}'
    
    if auth_header_value:
        outgoing_headers['Authorization'] = auth_header_value

    # Prepare data/json
    request_data = data
    if request_data is None and json_payload is not None:
        try:
            request_data = json.dumps(json_payload).encode('utf-8')
            # Ensure Content-Type is set for JSON if not already present
            if 'Content-Type' not in outgoing_headers:
                 outgoing_headers['Content-Type'] = 'application/json'
        except Exception as e:
            logger.error(f"Failed to encode JSON payload: {e}", exc_info=True)
            raise ValueError(f"Failed to encode JSON payload: {e}") from e

    if auth_header_value:
        if bearer_token:
            logger.info(f"Making authenticated request to {url} using provided token.")
        else: # Must have been an audience-fetched token
            logger.info(f"Making authenticated request to {url} (audience: {audience})")
    else:
        logger.warning(f"Making unauthenticated request to {url} as no audience or bearer_token was provided, or ID token could not be fetched.")

    try:
        response = session.request(
            method=method,
            url=url,
            headers=outgoing_headers,
            data=request_data,
            timeout=timeout,
            stream=False # Usually not needed for simple API calls like on_search
        )

        # Log outgoing auth header for debugging (truncated)
        # Access the request headers from the response object
        if auth_header_value: # Only log if we attempted to send an Authorization header
            sent_auth_header = response.request.headers.get('Authorization')
            if sent_auth_header:
                logger.info(f"DEBUG: Outgoing Request Authorization Header to {url}: {sent_auth_header[:20]}... (truncated for safety)")
            else: # Should not happen if id_token was set and added
                logger.warning(f"DEBUG: Outgoing Request to {url} was intended to be authenticated but did not include an Authorization header in the final request.")


        logger.info(f"Received response from {url}: Status={response.status_code}")

        return response

    except requests.exceptions.RequestException as e:
        logger.error(f"Error making authenticated request to {url}: {e}", exc_info=True)
        raise # Re-raise the exception after logging