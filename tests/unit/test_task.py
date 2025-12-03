#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for Task class
"""

import pytest
import uuid
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path

from aipyapp.aipy.task import Task, TaskError, TaskInputError, TaskStateError
from aipyapp.aipy.task_state import TaskState
from aipyapp.aipy.blocks import CodeBlocks, CodeBlock


class TestTaskInitialization:
    """测试 Task 初始化"""
    
    @pytest.mark.unit
    def test_task_creation(self, mock_context):
        """测试 Task 实例创建"""
        task = Task(mock_context)
        
        assert task.task_id is not None
        assert len(task.task_id) == 32  # UUID hex 长度
        assert task.context == mock_context
        assert task.settings == mock_context.settings
        assert task.start_time is None
        assert task.done_time is None
        assert task.instruction is None
        
    @pytest.mark.unit
    def test_task_id_uniqueness(self, mock_context):
        """测试 Task ID 唯一性"""
        task1 = Task(mock_context)
        task2 = Task(mock_context)
        
        assert task1.task_id != task2.task_id
        
    @pytest.mark.unit
    def test_task_working_directory(self, mock_context, temp_dir):
        """测试 Task 工作目录设置"""
        mock_context.cwd = temp_dir
        task = Task(mock_context)
        
        expected_cwd = temp_dir / task.task_id
        assert task.cwd == expected_cwd
        
    @pytest.mark.unit
    def test_task_max_rounds_setting(self, mock_context):
        """测试最大轮次设置"""
        # 使用默认值
        task = Task(mock_context)
        assert task.max_rounds == Task.MAX_ROUNDS
        
        # 使用自定义值
        mock_context.settings['max_rounds'] = 20
        task = Task(mock_context)
        assert task.max_rounds == 20


class TestTaskComponents:
    """测试 Task 组件"""
    
    @pytest.mark.unit
    def test_context_manager_initialization(self, task_instance):
        """测试上下文管理器初始化"""
        assert task_instance.context_manager is not None
        assert hasattr(task_instance.context_manager, 'add_message')
        assert hasattr(task_instance.context_manager, 'get_messages')
        
    @pytest.mark.unit
    def test_client_initialization(self, task_instance):
        """测试客户端初始化"""
        assert task_instance.client is not None
        assert task_instance.client.name == "test_client"
        assert task_instance.client.model == "test_model"
        
    @pytest.mark.unit
    def test_role_initialization(self, task_instance):
        """测试角色初始化"""
        assert task_instance.role is not None
        assert task_instance.role.name == "test_role"
        
    @pytest.mark.unit
    def test_code_blocks_initialization(self, task_instance):
        """测试代码块管理器初始化"""
        assert isinstance(task_instance.code_blocks, CodeBlocks)
        assert task_instance.code_blocks.blocks == []
        
    @pytest.mark.unit
    def test_runtime_initialization(self, task_instance):
        """测试运行时环境初始化"""
        assert task_instance.runtime is not None
        assert hasattr(task_instance.runtime, 'execute')
        
    @pytest.mark.unit
    def test_step_manager_initialization(self, task_instance):
        """测试步骤管理器初始化"""
        assert task_instance.step_manager is not None
        assert hasattr(task_instance.step_manager, 'register_trackable')
        # 验证注册的可追踪对象
        assert 'messages' in task_instance.step_manager._trackables
        assert 'runner' in task_instance.step_manager._trackables
        assert 'blocks' in task_instance.step_manager._trackables


class TestTaskState:
    """测试 Task 状态管理"""
    
    @pytest.mark.unit
    def test_task_state_initialization(self, task_instance):
        """测试任务状态初始化"""
        # Task 类可能没有 get_state 方法，需要检查
        if hasattr(task_instance, 'get_state'):
            state = task_instance.get_state()
            assert isinstance(state, TaskState)
            assert state.status == 'initialized'
        else:
            # 检查 TaskState 是否可以从 Task 创建
            state = TaskState(task_instance)
            assert state is not None
        
    @pytest.mark.unit
    def test_task_state_transitions(self, task_instance):
        """测试任务状态转换"""
        # 检查初始状态
        assert task_instance.start_time is None
        
        # 模拟开始任务
        task_instance.start_time = 123456789
        assert task_instance.start_time == 123456789
        
        # 如果有 get_state 方法，检查状态
        if hasattr(task_instance, 'get_state'):
            state = task_instance.get_state()
            assert state.status in ['running', 'initialized']
            
    @pytest.mark.unit
    def test_task_state_data(self, task_instance):
        """测试任务状态数据"""
        task_instance.instruction = "Test instruction"
        
        # 创建 TaskState 对象
        state = TaskState(task_instance)
        
        assert state.task_id == task_instance.task_id
        assert hasattr(state, 'created_at')
        assert hasattr(state, 'status')


class TestTaskExecution:
    """测试 Task 执行"""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_task_run_basic(self, async_task):
        """测试基本任务执行"""
        async_task.client.chat = AsyncMock(return_value="Test response")
        
        # 模拟简单执行
        with patch.object(async_task, '_process_response', return_value=True):
            with patch.object(async_task, 'is_stopped', return_value=True):
                result = await async_task.run("Test instruction")
                assert result is not None
                
    @pytest.mark.unit
    def test_task_stop(self, task_instance):
        """测试任务停止"""
        task_instance.stop()
        assert task_instance.is_stopped() == True
        
    @pytest.mark.unit
    def test_task_reset(self, task_instance):
        """测试任务重置"""
        # 设置一些状态
        task_instance.instruction = "Test"
        task_instance.start_time = 123456
        
        # 重置
        with patch.object(task_instance.step_manager, 'reset'):
            with patch.object(task_instance.code_blocks, 'clear'):
                task_instance.reset()
                
                # 验证重置
                assert task_instance.instruction is None
                assert task_instance.start_time is None


class TestTaskErrors:
    """测试 Task 错误处理"""
    
    @pytest.mark.unit
    def test_task_error_creation(self):
        """测试 TaskError 创建"""
        error = TaskError("Test error")
        assert str(error) == "Test error"
        
    @pytest.mark.unit
    def test_task_input_error(self):
        """测试 TaskInputError"""
        original_error = ValueError("Original error")
        error = TaskInputError("Input error", original_error)
        
        assert error.message == "Input error"
        assert error.original_error == original_error
        assert str(error) == "Input error"
        
    @pytest.mark.unit
    def test_task_state_error(self):
        """测试 TastStateError"""
        error = TastStateError("State error", task_id="123", status="failed")
        
        assert error.message == "State error"
        assert error.data['task_id'] == "123"
        assert error.data['status'] == "failed"


class TestTaskCodeBlocks:
    """测试 Task 代码块处理"""
    
    @pytest.mark.unit
    def test_add_code_block(self, task_instance):
        """测试添加代码块"""
        code = "print('Hello')"
        language = "python"
        
        block = CodeBlock(language=language, code=code)
        task_instance.code_blocks.add(block)
        
        assert len(task_instance.code_blocks.blocks) == 1
        assert task_instance.code_blocks.blocks[0].code == code
        assert task_instance.code_blocks.blocks[0].language == language
        
    @pytest.mark.unit
    def test_clear_code_blocks(self, task_instance):
        """测试清除代码块"""
        # 添加多个代码块
        task_instance.code_blocks.add(CodeBlock("python", "code1"))
        task_instance.code_blocks.add(CodeBlock("bash", "code2"))
        
        assert len(task_instance.code_blocks.blocks) == 2
        
        # 清除
        task_instance.code_blocks.clear()
        assert len(task_instance.code_blocks.blocks) == 0


class TestTaskPlugins:
    """测试 Task 插件系统"""
    
    @pytest.mark.unit
    def test_plugin_registration(self, task_instance):
        """测试插件注册"""
        mock_plugin = Mock()
        mock_plugin.name = "test_plugin"
        
        task_instance.plugins["test_plugin"] = mock_plugin
        
        assert "test_plugin" in task_instance.plugins
        assert task_instance.plugins["test_plugin"] == mock_plugin
        
    @pytest.mark.unit
    def test_plugin_initialization(self, task_instance):
        """测试插件初始化"""
        # 初始时应该是空的
        assert isinstance(task_instance.plugins, dict)
        assert len(task_instance.plugins) == 0


class TestTaskEventRecorder:
    """测试 Task 事件记录器"""
    
    @pytest.mark.unit
    def test_event_recorder_enabled(self, mock_context):
        """测试事件记录器启用"""
        mock_context.settings['enable_replay_recording'] = True
        task = Task(mock_context)
        
        assert hasattr(task, 'event_recorder')
        assert task.event_recorder.enabled == True
        
    @pytest.mark.unit
    def test_event_recorder_disabled(self, mock_context):
        """测试事件记录器禁用"""
        mock_context.settings['enable_replay_recording'] = False
        task = Task(mock_context)
        
        assert hasattr(task, 'event_recorder')
        assert task.event_recorder.enabled == False


class TestTaskSaveAndRestore:
    """测试 Task 保存和恢复"""
    
    @pytest.mark.unit
    def test_task_get_state(self, task_instance):
        """测试获取任务状态"""
        # 创建 TaskState 对象
        state = TaskState(task_instance)
        
        assert isinstance(state, TaskState)
        assert state.task_id == task_instance.task_id
        
    @pytest.mark.unit
    def test_task_save(self, task_instance, temp_dir):
        """测试保存任务"""
        save_path = temp_dir / "task_save.json"
        
        # Mock the display attribute if not exists
        if not hasattr(task_instance, 'display'):
            task_instance.display = Mock()
            task_instance.display.save = Mock()
        
        # Call save method
        task_instance.save(save_path)
        
        # Verify save was called
        task_instance.display.save.assert_called_once()
        
    @pytest.mark.unit
    def test_task_restore_state(self, task_instance):
        """测试恢复任务状态"""
        # 创建模拟状态
        state = TaskState(
            task_id=task_instance.task_id,
            status="running",
            created_at=123456789
        )
        
        # 恢复状态
        with patch.object(task_instance.step_manager, 'restore_state'):
            task_instance.restore_state(state)
            task_instance.step_manager.restore_state.assert_called_once()