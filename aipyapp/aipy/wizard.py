from collections import OrderedDict
import questionary
import requests

from loguru import logger

from .. import T
from ..config.llm import LLMConfig, PROVIDERS
from .trustoken import TrustToken

def get_models(providers, provider, api_key: str) -> list:
    """获取可用的模型列表"""
    provider_info = providers[provider]
    headers = {
        "Content-Type": "application/json"
    }
    
    if provider == "Claude":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.get(
            f"{provider_info['api_base']}{provider_info['models_endpoint']}",
            headers=headers
        )
        logger.info(f"获取模型列表: {response.text}")
        if response.status_code == 200:
            data = response.json()
            logger.info(f"获取模型列表成功: {data}")
            if provider in ["OpenAI", "DeepSeek", "MiniMax", "xAI", "Claude"]:
                return [model["id"] for model in data["data"]]
            elif provider == "Gemini":
                return [model["name"] for model in data["models"]]
            return []
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}")
        return []  # 如果API调用失败，返回空列表

def select_provider(llm_config, default='Trustoken'):
    """选择提供商"""
    while True:
        name = questionary.select(
            T('Select LLM Provider'),
            choices=[
                questionary.Choice(title=T('Trustoken is an intelligent API Key management service'), value='Trustoken', description=T('Recommended for beginners, easy to configure and feature-rich')),
                questionary.Choice(title=T('Other'), value='other')
            ],
            default=default
        ).unsafe_ask()
        if name == default:
            return default

        names = [name for name in llm_config.providers.keys() if name != default]
        names.append('<--')
        name = questionary.select(
            T('Select other providers'),
            choices=names
        ).unsafe_ask()
        if name != '<--':
            return name


def config_llm(llm_config):
    """配置 LLM 提供商"""
    # 第一步：选择提供商
    name = select_provider(llm_config)
    if not name:
        return None
    provider = llm_config.providers[name]
    config = {"type": provider["type"]}

    if name == 'Trustoken':
        def save_token(token):
            config['api_key'] = token

        tt = TrustToken()
        if not tt.fetch_token(save_token):
            return None
        
        config['model'] = 'auto'
    else:
        api_key = questionary.text(
                T('Enter your API key'),
                validate=lambda x: len(x) > 8
        ).unsafe_ask()
        config['api_key'] = api_key

        # 获取可用模型列表
        available_models = get_models(llm_config.providers, name, api_key)
        if not available_models:
            logger.warning(T('Model list acquisition failed'))
            return None

        # 第三步：选择模型
        model = questionary.select(
            T('Available Models'),
            choices=available_models
        ).unsafe_ask()
        config['model'] = model

    # 保存配置
    config['enable'] = True
    current_config = llm_config.config
    current_config[name] = config
    llm_config.save_config(current_config)
    return current_config
    