import requests
from app.models import MessageRequest

class GPTClient:
    BASE_URL =  "http://host.docker.internal:8200/api/v1/generate-response"
    # BASE_URL = "http://localhost:8200/api/v1/generate-response"

    @staticmethod
    def send_message(request: MessageRequest):
        """
        Sends a message to the GPT API and retrieves the response.

        :param request: MessageRequest object containing the message payload.
        :return: JSON response from the GPT API.
        :raises RuntimeError: If the request fails.
        """
        payload = request.to_payload()
        try:
            response = requests.post(
                GPTClient.BASE_URL, json=payload, timeout=600
            )  # Make the API request
            response.raise_for_status()  # Raise an error for HTTP codes >= 400
            return response.json()  # Return the JSON response
        except requests.RequestException as e:
            raise RuntimeError(f"GPT request failed: {e}")
