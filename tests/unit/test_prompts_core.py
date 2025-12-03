#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Core tests for prompts module - essential functionality only
"""

import pytest
import tempfile
import time
import shutil
from pathlib import Path
from unittest.mock import Mock
from threading import Thread

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aipyapp.aipy.prompts import (
    check_commands,
    PromptFeatures,
    Prompts,
    _command_cache
)


class TestPromptFeaturesCore:
    """核心 PromptFeatures 测试"""

    @pytest.mark.unit
    def test_empty_features(self):
        """测试空功能"""
        features = PromptFeatures()
        assert features.features == {}
        assert not features.has('any_feature')

    @pytest.mark.unit
    def test_features_with_dict(self):
        """测试字典初始化"""
        features_dict = {'survey': True, 'debug': False}
        features = PromptFeatures(features_dict)
        assert features.has('survey')
        assert not features.has('debug')
        assert features.get('debug') is False
        assert features.get('debug', True) is False  # 默认值被忽略

    @pytest.mark.unit
    def test_features_operations(self):
        """测试功能操作"""
        features = PromptFeatures()
        features.set('new_feature', True)
        assert features.has('new_feature')

        features.update({'another': True})
        assert features.has('another')
        assert features.has('new_feature')  # 原有功能保留

        result = features.to_dict()
        assert result['new_feature'] is True
        assert result['another'] is True


class TestCheckCommandsCore:
    """核心 check_commands 测试"""

    @pytest.mark.unit
    def test_command_existence_check(self):
        """测试命令存在性检查"""
        # 使用一些常见命令
        commands = {'python3': ['--version']}

        result = check_commands(commands)

        assert isinstance(result, dict)
        assert 'python3' in result

        # 结果应该是字符串路径或 None
        path = result['python3']
        assert isinstance(path, (str, type(None)))

    @pytest.mark.unit
    def test_nonexistent_command(self):
        """测试不存在的命令"""
        commands = {'definitely_nonexistent_xyz': ['--version']}

        result = check_commands(commands)

        assert isinstance(result, dict)
        assert result['definitely_nonexistent_xyz'] is None

    @pytest.mark.unit
    def test_caching_mechanism(self):
        """测试缓存机制"""
        # 清除缓存
        _command_cache.clear()
        commands = {'python3': ['--version']}

        # 第一次调用
        result1 = check_commands(commands)

        # 第二次调用
        result2 = check_commands(commands)

        # 结果应该相同
        assert result1 == result2
        assert result1 == result2

    @pytest.mark.unit
    def test_empty_commands(self):
        """测试空命令字典"""
        result = check_commands({})
        assert result == {}

    @pytest.mark.unit
    def test_check_commands_return_type(self):
        """测试返回类型"""
        commands = {'python3': ['--version']}
        result = check_commands(commands)

        assert isinstance(result, dict)
        for cmd, path in result.items():
            assert isinstance(cmd, str)
            assert isinstance(path, (str, type(None)))


class TestPromptsCore:
    """核心 Prompts 测试"""

    @pytest.mark.unit
    def test_basic_creation(self):
        """测试基本创建"""
        prompts = Prompts()

        assert prompts.template_dir is not None
        assert prompts.env is not None
        assert prompts.features is not None
        assert hasattr(prompts.env, 'get_template')
        assert prompts.env.auto_reload is True

    @pytest.mark.unit
    def test_features_parameter(self):
        """测试功能参数"""
        features = {'survey': True, 'debug': False}
        prompts = Prompts(features=features)

        assert prompts.features.has('survey')
        assert not prompts.features.has('debug')

    @pytest.mark.unit
    def test_environment_caching(self):
        """测试环境缓存"""
        # 清除缓存
        Prompts._env_cache.clear()

        prompts1 = Prompts()
        prompts2 = Prompts()

        # 相同目录的实例应该共享环境
        assert prompts1.env is prompts2.env
        assert len(Prompts._env_cache) == 1

    @pytest.mark.unit
    def test_custom_directory(self, temp_dir):
        """测试自定义目录"""
        prompts = Prompts(template_dir=str(temp_dir))

        assert prompts.template_dir == str(temp_dir)
        assert prompts.env is not None

    @pytest.mark.unit
    def test_template_not_found_error(self):
        """测试模板不存在的错误"""
        prompts = Prompts()

        with pytest.raises(FileNotFoundError):
            prompts.get_prompt('nonexistent_template_xyz')


class TestPromptsGlobalSetup:
    """测试全局设置相关代码路径"""

    @pytest.mark.unit
    def test_env_globals_setup(self):
        """测试环境全局变量设置"""
        prompts = Prompts()

        # 验证命令全局变量
        assert 'commands' in prompts.env.globals
        assert 'node' in prompts.env.globals['commands']
        assert 'bash' in prompts.env.globals['commands']

    @pytest.mark.unit
    def test_env_filters_setup(self):
        """测试环境过滤器设置"""
        prompts = Prompts()

        # 验证过滤器被注册
        assert 'tojson' in prompts.env.filters

    @pytest.mark.unit
    def test_instance_globals_features_registration(self):
        """测试实例features对象注册"""
        prompts = Prompts()

        # 验证features对象被注册到全局变量
        assert 'features' in prompts.env.globals
        features = prompts.env.globals['features']
        assert hasattr(features, 'has')
        assert hasattr(features, 'get')


class TestThreadSafety:
    """线程安全性测试"""

    @pytest.mark.unit
    def test_concurrent_creation(self):
        """测试并发创建"""
        # 清除缓存
        Prompts._env_cache.clear()
        _command_cache.clear()

        results = []
        errors = []

        def create_instance():
            try:
                prompts = Prompts()
                results.append(len(prompts.features.features))
            except Exception as e:
                errors.append(str(e))

        # 创建多个线程同时创建 Prompts 实例
        threads = []
        for i in range(3):
            t = Thread(target=create_instance)
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 验证没有错误
        assert len(errors) == 0
        assert len(results) == 3

        # 验证环境缓存正常
        assert len(Prompts._env_cache) == 1


class TestPromptsIntegration:
    """Prompts 集成测试"""

    @pytest.mark.unit
    def test_custom_template(self, temp_dir):
        """测试自定义模板"""
        # 创建一个简单的模板
        template_file = temp_dir / 'test.j2'
        template_content = 'Hello {{ name }}!'
        template_file.write_text(template_content)

        prompts = Prompts(template_dir=str(temp_dir))
        result = prompts.get_prompt('test', name='World')

        assert result == 'Hello World!'

    @pytest.mark.unit
    def test_template_modification_detection(self, temp_dir):
        """测试模板修改检测"""
        # 创建模板
        template_file = temp_dir / 'dynamic.j2'
        template_file.write_text('Version 1')

        prompts = Prompts(template_dir=str(temp_dir))
        result1 = prompts.get_prompt('dynamic')
        assert result1 == 'Version 1'

        # 等待确保文件时间戳不同
        time.sleep(0.1)

        # 修改模板
        template_file.write_text('Version 2')

        # 由于 auto_reload=True，应该自动检测到变化
        result2 = prompts.get_prompt('dynamic')
        assert result2 == 'Version 2'


@pytest.fixture(autouse=True)
def reset_caches():
    """重置缓存，避免测试间干扰"""
    # 重置命令缓存
    _command_cache.clear()

    # 重置环境缓存
    Prompts._env_cache.clear()

    yield

    # 清理操作
    _command_cache.clear()
    Prompts._env_cache.clear()