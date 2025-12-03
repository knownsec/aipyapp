#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Pytest configuration and shared fixtures
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import Generator, Any, Dict

import pytest
import pytest_asyncio

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 安全导入，处理缺失的模块
try:
    from aipyapp.aipy import Task, TaskManager, ConfigManager
except ImportError:
    Task = None
    TaskManager = None
    ConfigManager = None

try:
    from aipyapp.aipy.context import ContextManager, ContextConfig
except ImportError:
    ContextManager = None
    ContextConfig = None

try:
    from aipyapp.aipy.runtime import CliPythonRuntime
except ImportError:
    CliPythonRuntime = None

try:
    from aipyapp.exec import BlockExecutor
except ImportError:
    BlockExecutor = None


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """提供测试数据目录路径"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="function")
def temp_dir() -> Generator[Path, None, None]:
    """创建临时目录用于测试"""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    # 清理
    if temp_path.exists():
        shutil.rmtree(temp_path)


@pytest.fixture
def mock_settings(temp_dir) -> Mock:
    """创建模拟的设置对象"""
    settings = Mock()
    settings_dict = {
        'config_dir': temp_dir / '.config',
        'workspace_dir': temp_dir / 'workspace',
        'max_rounds': 10,
        'enable_replay_recording': False,
        'gui': False,
        'context_manager': {
            'max_messages': 100,
            'max_tokens': 10000,
            'compression_threshold': 0.8
        },
        'workdir': None,
        'environ': {},
        'role': 'aipy',
        'api': {},
        '_config_dir': temp_dir / '.config',
        'share_result': False
    }
    settings.get = Mock(side_effect=lambda key, default=None: settings_dict.get(key, default))
    settings.gui = False
    settings.workdir = None
    settings.__getitem__ = settings.get
    # 添加属性访问
    for key, value in settings_dict.items():
        setattr(settings, key, value)
    return settings


@pytest.fixture
def mock_context(mock_settings, temp_dir):
    """创建模拟的上下文对象"""
    context = Mock()
    context.settings = mock_settings
    context.cwd = temp_dir
    context.mcp = None
    context.gui = False
    
    # 模拟 prompts
    mock_prompts = Mock()
    mock_prompts.get_default_prompt = Mock(return_value="Default prompt")
    mock_prompts.get_task_prompt = Mock(return_value="Task prompt")
    mock_prompts.get_chat_prompt = Mock(return_value="Chat prompt")
    mock_prompts.get_parse_error_prompt = Mock(return_value="Parse error prompt")
    mock_prompts.get_results_prompt = Mock(return_value="Results prompt")
    mock_prompts.get_mixed_results_prompt = Mock(return_value="Mixed results prompt")
    mock_prompts.get_edit_results_prompt = Mock(return_value="Edit results prompt")
    mock_prompts.get_mcp_result_prompt = Mock(return_value="MCP result prompt")
    context.prompts = mock_prompts
    
    # 模拟 client_manager
    mock_client = Mock()
    mock_client.name = "test_client"
    mock_client.model = "test_model"
    mock_client.has_capability = Mock(return_value=True)
    mock_client.chat = Mock(return_value="Mock response")
    context.client_manager = Mock()
    context.client_manager.Client = Mock(return_value=mock_client)
    
    # 模拟 role_manager
    mock_role = Mock()
    mock_role.name = "test_role"
    mock_role.prompt = "Test role prompt"
    mock_role.plugins = {}
    context.role_manager = Mock()
    context.role_manager.current_role = mock_role
    
    # 模拟 plugin_manager
    mock_plugin_manager = Mock()
    mock_plugin_manager.create_task_plugin = Mock(return_value=None)
    context.plugin_manager = mock_plugin_manager
    
    # 模拟 display_manager
    mock_display_manager = Mock()
    mock_display_manager.create_display_plugin = Mock(return_value=Mock())
    context.display_manager = mock_display_manager
    
    # 模拟 diagnose
    mock_diagnose = Mock()
    mock_diagnose.report_code_error = Mock()
    context.diagnose = mock_diagnose
    
    return context


@pytest.fixture
def task_instance(mock_context) -> Task:
    """创建 Task 实例用于测试"""
    return Task(mock_context)


@pytest.fixture
def mock_llm_client():
    """创建模拟的 LLM 客户端"""
    client = AsyncMock()
    client.name = "mock_llm"
    client.model = "mock_model"
    client.chat = AsyncMock(return_value="Mock response")
    client.stream_chat = AsyncMock()
    return client


@pytest.fixture
def context_manager() -> ContextManager:
    """创建 ContextManager 实例"""
    config = ContextConfig(
        max_messages=50,
        max_tokens=5000,
        compression_threshold=0.8
    )
    return ContextManager(config)


@pytest.fixture
def block_executor() -> BlockExecutor:
    """创建 BlockExecutor 实例"""
    return BlockExecutor()


@pytest.fixture
def sample_config_file(temp_dir) -> Path:
    """创建示例配置文件"""
    config_file = temp_dir / "test_config.toml"
    config_content = """
[default]
max_rounds = 5
enable_replay = true

[llm]
default_model = "gpt-4"
temperature = 0.7

[paths]
workspace = "~/workspace"
"""
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def mock_task_manager(mock_settings):
    """创建模拟的 TaskManager"""
    tm = Mock(spec=TaskManager)
    tm.settings = mock_settings
    tm.get_tasks = Mock(return_value=[])
    tm.get_status = Mock(return_value={
        'client': 'test_client',
        'model': 'test_model',
        'tasks': 0
    })
    return tm


@pytest.fixture
def sample_code_block():
    """提供示例代码块"""
    return {
        'language': 'python',
        'code': 'print("Hello, Test!")',
        'metadata': {
            'line_number': 1,
            'source': 'test'
        }
    }


@pytest.fixture(autouse=True)
def reset_singletons():
    """重置单例对象，避免测试间干扰"""
    # 如果有单例模式的对象，在这里重置
    yield
    # 清理操作


@pytest.fixture
def mock_requests(monkeypatch):
    """模拟 requests 库"""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json = Mock(return_value={'status': 'ok'})
    mock_response.text = "Mock response"
    
    mock_get = Mock(return_value=mock_response)
    mock_post = Mock(return_value=mock_response)
    
    monkeypatch.setattr('requests.get', mock_get)
    monkeypatch.setattr('requests.post', mock_post)
    
    return {
        'get': mock_get,
        'post': mock_post,
        'response': mock_response
    }


# 异步测试 fixtures
@pytest_asyncio.fixture
async def async_task(mock_context):
    """创建异步 Task 实例"""
    task = Task(mock_context)
    yield task
    # 清理
    if hasattr(task, 'cleanup'):
        await task.cleanup()


# 标记慢速测试
def pytest_configure(config):
    """配置 pytest"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "llm: marks tests that require LLM access"
    )
    config.addinivalue_line(
        "markers", "mcp: marks tests for MCP functionality"
    )