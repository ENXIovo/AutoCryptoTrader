# api_manager_factory.py
from apis.openai_api import OpenAIAPI
from openai import OpenAI
from config import ENDPOINT_CONFIGS

# from api.bard_api import BardAPIManager


class APIManagerFactory:
    _clients = {}

    @staticmethod
    def initialize_clients():
        for group, config in ENDPOINT_CONFIGS.items():
            client = OpenAI(
                api_key=config["api_key"]
            )
            # 为这个端点组的所有模型分配同一个客户端实例
            for model_name in config["models"]:
                APIManagerFactory._clients[model_name] = OpenAIAPI(client)

    @staticmethod
    def get_api_manager(model_name: str):
        # 根据模型名称返回对应的API管理器实例
        if model_name in APIManagerFactory._clients:
            return APIManagerFactory._clients[model_name]
        else:
            raise ValueError(
                f"API manager for model '{model_name}' is not initialized."
            )
