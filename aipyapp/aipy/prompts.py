#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import os
import locale
import platform
import json
import shutil
from datetime import datetime
from typing import List, TYPE_CHECKING, Dict, Optional
from threading import RLock

from jinja2 import Environment, FileSystemLoader

from .. import __respath__
from .toolcalls import ToolCallResult

if TYPE_CHECKING:
    from .task import Task

class PromptFeatures:
    """
    灵活的功能开关管理类，支持任意字符串功能名称
    """
    def __init__(self, features: Optional[Dict[str, bool]] = None):
        self.features = features or {}

    def has(self, feature_name: str) -> bool:
        """检查功能是否存在且为true"""
        return self.features.get(feature_name, False)

    def enabled(self, feature_name: str) -> bool:
        """has的别名"""
        return self.has(feature_name)

    def get(self, feature_name: str, default: bool = False) -> bool:
        """获取功能值，支持默认值"""
        return self.features.get(feature_name, default)

    def set(self, feature_name: str, value: bool):
        """设置功能值"""
        self.features[feature_name] = value

    def update(self, features: Dict[str, bool]):
        """批量更新功能"""
        self.features.update(features)

    def to_dict(self) -> Dict[str, bool]:
        """转换为字典"""
        return self.features.copy()

# 类级别缓存，避免重复的命令查找
_command_cache: Dict[str, Optional[str]] = {}

def check_commands(commands) -> Dict[str, Optional[str]]:
    """
    检查多个命令是否存在，返回其可执行文件路径。
    这是一个性能优化的实现，只检查命令是否存在而不获取版本信息，
    避免了耗时的 subprocess 调用。

    :param commands: dict，键为命令名，值为获取版本的参数（当前未使用，保留以备将来扩展）
    :return: dict，例如 {"node": "/usr/bin/node", "bash": "/bin/bash", ...}，命令不存在时为 None
    """
    result = {}

    for cmd, version_args in commands.items():
        # 使用缓存避免重复的 shutil.which() 调用
        if cmd not in _command_cache:
            path = shutil.which(cmd)
            _command_cache[cmd] = path if path else None

        result[cmd] = _command_cache[cmd]

    return result

class Prompts:
    # 类级别缓存
    _env_cache: Dict[str, Environment] = {}
    _cache_lock = RLock()

    def __init__(self, template_dir: str = None, features: Optional[Dict[str, bool]] = None):
        if not template_dir:
            template_dir = __respath__ / 'prompts'
        self.template_dir = os.path.abspath(template_dir)

        # 使用类级别缓存的环境
        self.env = self._get_cached_env()

        # 为每个实例创建独立的 features（避免不同实例间的状态污染）
        self.features = PromptFeatures(features or {})

        # 注册实例特定的全局变量
        self._init_instance_globals()

    def _get_cached_env(self) -> Environment:
        """获取或创建缓存的环境"""
        with self._cache_lock:
            if self.template_dir not in self._env_cache:
                self._env_cache[self.template_dir] = Environment(
                    trim_blocks=True,
                    lstrip_blocks=True,
                    loader=FileSystemLoader(self.template_dir),
                    auto_reload=True,  # 自动检测模板文件变化并清理缓存
                    #autoescape=select_autoescape(['j2'])
                )
            return self._env_cache[self.template_dir]

    def _init_instance_globals(self) -> None:
        """注册实例特定的全局变量"""
        # 注册 commands（使用缓存）
        commands_to_check = {
            "node": ["--version"],
            "bash": ["--version"],
            #"powershell": ["-Command", "$PSVersionTable.PSVersion.ToString()"],
            "osascript": ["-e", 'return "AppleScript OK"']
        }
        self.env.globals['commands'] = check_commands(commands_to_check)

        # 注册 OS 信息
        osinfo = {'system': platform.system(), 'platform': platform.platform(), 'locale': locale.getlocale()}
        self.env.globals['os'] = osinfo
        self.env.globals['python_version'] = platform.python_version()

        # 注册过滤器
        self.env.filters['tojson'] = lambda x: json.dumps(x, ensure_ascii=False, default=str)

        # 注册实例特定的 features
        self.env.globals['features'] = self.features

    def get_prompt(self, template_name: str, **kwargs) -> str:
        """
        加载指定模板并用 kwargs 渲染
        :param template_name: 模板文件名（如 'my_prompt.txt'）
        :param kwargs: 用于模板渲染的关键字参数
        :return: 渲染后的字符串
        """
        template_name = f"{template_name}.j2"
        try:
            template = self.env.get_template(template_name)
        except Exception as e:
            # 提供更详细的错误上下文信息
            if hasattr(self.env, 'loader') and hasattr(self.env.loader, 'searchpath'):
                search_paths = self.env.loader.searchpath
            else:
                search_paths = [self.template_dir]

            error_msg = (
                f"Prompt template not found: {template_name}\n"
                f"Searched in directories: {search_paths}\n"
                f"Working directory: {os.getcwd()}\n"
                f"Original error: {type(e).__name__}: {e}"
            )
            raise FileNotFoundError(error_msg) from e

        try:
            return template.render(**kwargs)
        except Exception as e:
            # 模板渲染错误的详细信息
            error_msg = (
                f"Template rendering failed for: {template_name}\n"
                f"Template variables: {list(kwargs.keys())}\n"
                f"Original error: {type(e).__name__}: {e}"
            )
            raise RuntimeError(error_msg) from e

    def get_default_prompt(self, **kwargs) -> str:
        """
        使用 default.jinja 模板，自动补充部分变量后渲染
        :param role: 角色对象，用于加载角色特定的功能开关
        :param kwargs: 用户传入的模板变量
        :return: 渲染后的字符串
        """
        return self.get_prompt('default', **kwargs)

    def get_task_prompt(self, instruction: str, gui: bool = False, parent: Task | None = None, lang: str = None) -> str:
        """
        获取任务提示
        :param instruction: 用户输入的字符串
        :param gui: 是否使用 GUI 模式
        :param parent: 父任务（如果有）
        :return: 渲染后的字符串
        """
        contexts = {}
        contexts['Today'] = datetime.now().strftime('%Y-%m-%d')
        if not gui:
            contexts['TERM'] = os.environ.get('TERM', 'unknown')
        constraints = {"lang": lang}
        return self.get_prompt('task', instruction=instruction, contexts=contexts, constraints=constraints, gui=gui, parent=parent)
    
    def get_toolcall_results_prompt(self, results: List[ToolCallResult]) -> str:
        """
        获取混合结果提示（包含执行和编辑结果）
        :param results: 混合结果字典
        :return: 渲染后的字符串
        """
        return self.get_prompt('toolcall_results', results=results)
    
    def get_chat_prompt(self, instruction: str, task: str) -> str:
        """
        获取聊天提示
        :param instruction: 用户输入的字符串
        :param task: 初始任务
        :return: 渲染后的字符串
        """
        return self.get_prompt('chat', instruction=instruction, initial_task=task)
    
    def get_parse_error_prompt(self, errors: list) -> str:
        """
        获取消息解析错误提示
        :param errors: 错误列表
        :return: 渲染后的字符串
        """
        return self.get_prompt('parse_error', errors=errors)
    