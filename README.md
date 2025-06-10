1. Project Overview
This project acts as a Beckn Provider Platform (BPP) that exposes a product catalog. It enables Beckn Application Platforms (BAPs - consumer apps) to search for products. The BPP is designed for testing the Beckn /search and on_search message flows.
Key functionalities include:
Receiving /search requests from BAPs.
Immediately acknowledging search requests.
Asynchronously performing product searches based on criteria (product name, color, type) using a products.json dummy dataset.
Sending on_search responses (containing search results) to the BAP's callback URL.
Providing a debug endpoint (/get_search_results) to fetch search results directly by transaction_id.
The project uses an in-memory store for product data and pending requests, making it lightweight and suitable for local development and testing.

2. Folder Structure
Here's a simplified view of the project structure:
Plaintext
bpp-server-without-elastic/
├── app/
│   ├── controllers/            # Defines API endpoints (routes)
│   ├── services/               # Handles Beckn message formatting & search logic
│   ├── utils/                  # Manages asynchronous tasks & Beckn utilities
│   └── __init__.py             # Initializes Flask app, loads config & product data
├── data/
│   └── products.json           # Dummy product data
├── tests/                      # (Recommended for unit/integration tests)
├── .env                        # Environment variables (BPP_ID, BPP_URI, etc.)
├── config.py                   # Flask configuration classes
├── Dockerfile                  # Instructions to build the Docker image
├── docker-compose.yml          # Defines services for Docker Compose
├── requirements.txt            # Python dependencies
└── run.py                      # Entry point to run the Flask application

3. API Endpoints
The BPP exposes the following endpoints under the /beckn prefix:
3.1. /search
This is the primary endpoint for a BAP to initiate a product search. The BPP acknowledges the request immediately and processes the search asynchronously, sending results to the BAP's callback URL.
Method: POST
URL: http://localhost:5000/beckn/search
Request Body Example: A JSON payload containing context (e.g., bap_uri, transaction_id) and message.intent.item.descriptor.name for search criteria (e.g., "Shirt"). Optional tags can be used for filtering by "color" or "type".
Success Response (ACK): 202 Accepted with an ACK status in the message, including BPP-generated message_id and timestamp.

3.2. /on_search (BPP's endpoint to receive an on_search)
This endpoint is primarily for demonstration or testing scenarios where this BPP might need to receive an on_search message (e.g., if it were acting in a dual role). In the standard Beckn flow, this BPP sends on_search to the BAP's callback endpoint.
Method: POST
URL: http://localhost:5000/beckn/on_search
Request Body Example: A full on_search payload from another BPP.
Success Response: 200 OK with an ACK status.




3.3. /get_search_results/<transaction_id>
Significance: This is a utility/debug endpoint. It allows you to directly fetch the on_search results that the BPP has generated for a given transaction_id, bypassing the asynchronous callback to the BAP. This is useful for testing the search logic or if the BAP callback fails.
Method: GET


URL: http://localhost:5000/beckn/get_search_results/{transaction_id}

 Replace {transaction_id} with the actual ID from a previous /search request (e.g., http://localhost:5000/beckn/get_search_results/unique-transaction-id-123). For the example you provided, you'd use: http://localhost:5000/beckn/get_search_results/txn_no_es_003.


Request Body: None


Success Response (if results are ready):


Status Code: 200 OK
Body Example (JSON - this is the full on_search payload):



4. Running the Project
4.1. Locally (without Docker)
Prerequisites: Python 3.7+, pip
Setup & Run:
Clone the repository and navigate to bpp-server-without-elastic/.
Create a virtual environment:

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

Install dependencies:

pip install -r requirements.txt

Create a .env file in the project root with your BPP details (e.g., BPP_ID="my-bpp-id-local", BPP_URI="http://localhost:5000/beckn").
Run the application:

python run.py
The application will typically start on http://0.0.0.0:5000/.
4.2. Using Docker
Setup & Run:
Ensure you have Dockerfile and docker-compose.yml in the project root, as described in the original documentation.
Ensure you have the .env file created as described in the "Locally" section.
Navigate to the project root directory.
Build the image and start the container:
 Bash

docker-compose up --build

 To run in detached mode (in the background):
 Bash

docker-compose up --build -d

 The application will be accessible at http://localhost:5000.
Stopping the Docker Container:
Bash
docker-compose down

5. Future Enhancements
This project provides a basic BPP simulation. For more robust and scalable solutions, consider these enhancements:
Persistent Storage: Replace in-memory data with databases (e.g., PostgreSQL, MongoDB) for larger datasets and persistent storage.
Advanced Search Capabilities: Integrate dedicated search engines like Elasticsearch or Apache Solr for faster, more relevant full-text search, and advanced features.
Authentication and Authorization: Implement Beckn's signing mechanism for secure communication.
Scalability: Design for higher load, potentially using container orchestration (e.g., Kubernetes) and load balancing.
Comprehensive Logging and Monitoring: Integrate advanced tools for production environments.
Support for Other Beckn Actions: Extend to support select, init, confirm, status, etc., to simulate a complete e-commerce transaction flow.
Dynamic Provider and Catalog Management: Allow dynamic addition/update of providers and product catalogs.

