# chatgpt.py
from typing import Dict

class APIManager:
    def __init__(self):
        pass

    def format_input_messages(self, user_message: str) -> list:
        """
        Format the input messages. This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")

    def prepare_request(self, prompt: str) -> Dict:
        """
        Prepare the API request. This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")

    def handle_response(self, response: dict, user_message: str) -> str:
        """
        Handle the API response. This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")

    def generate_response(self, session):
        """
        Asynchronously generate a response from the API. This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")

    def generate_response_stream(self, session):
        """
        Asynchronously generate a response stream from the API. This method should be implemented by subclasses.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")
