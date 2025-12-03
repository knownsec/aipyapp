#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit tests for TaskManager class
"""

import pytest
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from collections import deque

from aipyapp.aipy.taskmgr import TaskManager
from aipyapp.aipy.task import Task


class TestTaskManagerInitialization:
    """测试 TaskManager 初始化"""
    
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_task_manager_creation(self, mock_prompts, mock_diagnose, 
                                  mock_mcp, mock_role_mgr, mock_client_mgr, 
                                  mock_plugin_mgr, mock_settings):
        """测试 TaskManager 实例创建"""
        tm = TaskManager(mock_settings)
        
        assert tm.settings == mock_settings
        assert isinstance(tm.tasks, deque)
        assert tm.tasks.maxlen == TaskManager.MAX_TASKS
        assert tm.task_context is not None
        
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_task_manager_with_display(self, mock_prompts, mock_diagnose,
                                      mock_mcp, mock_role_mgr, mock_client_mgr,
                                      mock_plugin_mgr, mock_settings):
        """测试带显示管理器的 TaskManager"""
        mock_display = Mock()
        tm = TaskManager(mock_settings, display_manager=mock_display)
        
        assert tm.display_manager == mock_display
        
    @pytest.mark.unit
    def test_max_tasks_limit(self):
        """测试最大任务数限制"""
        assert TaskManager.MAX_TASKS == 16


class TestTaskManagerWorkEnvironment:
    """测试 TaskManager 工作环境"""
    
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_init_workenv_with_workdir(self, mock_prompts, mock_diagnose,
                                      mock_mcp, mock_role_mgr, mock_client_mgr,
                                      mock_plugin_mgr, mock_settings, temp_dir):
        """测试工作目录初始化"""
        mock_settings['workdir'] = 'test_workspace'
        
        with patch('os.chdir') as mock_chdir:
            with patch('pathlib.Path.cwd', return_value=temp_dir):
                tm = TaskManager(mock_settings)
                
                expected_workdir = temp_dir / 'test_workspace'
                assert tm.cwd == expected_workdir
                mock_chdir.assert_called_once_with(expected_workdir)
                
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_init_workenv_without_workdir(self, mock_prompts, mock_diagnose,
                                         mock_mcp, mock_role_mgr, mock_client_mgr,
                                         mock_plugin_mgr, mock_settings):
        """测试无工作目录时的初始化"""
        mock_settings['workdir'] = None
        
        with patch('pathlib.Path.cwd', return_value=Path('/current/dir')):
            tm = TaskManager(mock_settings)
            assert tm.cwd == Path('/current/dir')
            
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_environment_variables(self, mock_prompts, mock_diagnose,
                                  mock_mcp, mock_role_mgr, mock_client_mgr,
                                  mock_plugin_mgr, mock_settings):
        """测试环境变量设置"""
        mock_settings['environ'] = {
            'TEST_VAR1': 'value1',
            'TEST_VAR2': 'value2'
        }
        
        with patch.dict(os.environ, {}, clear=True):
            tm = TaskManager(mock_settings)
            
            assert os.environ.get('TEST_VAR1') == 'value1'
            assert os.environ.get('TEST_VAR2') == 'value2'


class TestTaskManagerComponents:
    """测试 TaskManager 组件"""
    
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_plugin_manager_initialization(self, mock_prompts, mock_diagnose,
                                          mock_mcp, mock_role_mgr, mock_client_mgr,
                                          mock_plugin_mgr, mock_settings):
        """测试插件管理器初始化"""
        mock_plugin_instance = mock_plugin_mgr.return_value
        
        tm = TaskManager(mock_settings)
        
        mock_plugin_mgr.assert_called_once()
        mock_plugin_instance.add_plugin_directory.assert_called()
        mock_plugin_instance.load_all_plugins.assert_called_once()
        assert tm.plugin_manager == mock_plugin_instance
        
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_client_manager_initialization(self, mock_prompts, mock_diagnose,
                                          mock_mcp, mock_role_mgr, mock_client_mgr,
                                          mock_plugin_mgr, mock_settings):
        """测试客户端管理器初始化"""
        mock_client_instance = mock_client_mgr.return_value
        
        tm = TaskManager(mock_settings)
        
        mock_client_mgr.assert_called_once_with(mock_settings)
        assert tm.client_manager == mock_client_instance
        
    @pytest.mark.unit
    @patch('aipyapp.aipy.taskmgr.PluginManager')
    @patch('aipyapp.aipy.taskmgr.ClientManager')
    @patch('aipyapp.aipy.taskmgr.RoleManager')
    @patch('aipyapp.aipy.taskmgr.MCPToolManager')
    @patch('aipyapp.aipy.taskmgr.Diagnose')
    @patch('aipyapp.aipy.taskmgr.Prompts')
    def test_role_manager_initialization(self, mock_prompts, mock_diagnose,
                                        mock_mcp, mock_role_mgr, mock_client_mgr,
                                        mock_plugin_mgr, mock_settings):
        """测试角色管理器初始化"""
        mock_settings['role'] = 'test_role'
        mock_settings['api'] = {'key': 'value'}
        mock_role_instance = mock_role_mgr.return_value
        
        tm = TaskManager(mock_settings)
        
        mock_role_mgr.assert_called_once()
        mock_role_instance.load_roles.assert_called_once()
        mock_role_instance.use.assert_called_once_with('test_role')
        assert tm.role_manager == mock_role_instance


class TestTaskManagement:
    """测试任务管理功能"""
    
    @pytest.mark.unit
    def test_new_task_creation(self, mock_task_manager):
        """测试创建新任务"""
        # 模拟 task_context
        mock_task_manager.task_context = Mock(spec=TaskContext)
        
        # 模拟 new 方法
        mock_task = Mock(spec=Task)
        mock_task_manager.new = Mock(return_value=mock_task)
        
        task = mock_task_manager.new()
        
        # 验证返回值
        assert task == mock_task
        mock_task_manager.new.assert_called_once()
        
    @pytest.mark.unit
    def test_get_current_task(self, mock_task_manager):
        """测试获取当前任务"""
        mock_task = Mock(spec=Task)
        mock_task_manager.tasks = deque([mock_task])
        mock_task_manager.current = Mock(return_value=mock_task)
        
        current = mock_task_manager.current()
        assert current == mock_task
        
    @pytest.mark.unit
    def test_get_current_task_empty(self, mock_task_manager):
        """测试空队列时获取当前任务"""
        mock_task_manager.tasks = deque()
        mock_task_manager.current = Mock(return_value=None)
        
        current = mock_task_manager.current()
        assert current is None
        
    @pytest.mark.unit
    def test_get_tasks_list(self, mock_task_manager):
        """测试获取任务列表"""
        task1 = Mock(spec=Task)
        task2 = Mock(spec=Task)
        mock_task_manager.tasks = deque([task1, task2])
        mock_task_manager.get_tasks = Mock(return_value=[task1, task2])
        
        tasks = mock_task_manager.get_tasks()
        assert tasks == [task1, task2]
        
    @pytest.mark.unit
    def test_switch_task(self, mock_task_manager):
        """测试切换任务"""
        task1 = Mock(spec=Task, task_id='task1')
        task2 = Mock(spec=Task, task_id='task2')
        task3 = Mock(spec=Task, task_id='task3')
        mock_task_manager.tasks = deque([task1, task2, task3])
        mock_task_manager.switch = Mock(return_value=True)
        
        # 切换到 task2
        result = mock_task_manager.switch('task2')
        assert result == True
        mock_task_manager.switch.assert_called_once_with('task2')
        
    @pytest.mark.unit
    def test_switch_task_not_found(self, mock_task_manager):
        """测试切换到不存在的任务"""
        task1 = Mock(spec=Task, task_id='task1')
        mock_task_manager.tasks = deque([task1])
        mock_task_manager.switch = Mock(return_value=False)
        
        result = mock_task_manager.switch('task_not_exist')
        assert result == False


class TestTaskManagerStatus:
    """测试 TaskManager 状态"""
    
    @pytest.mark.unit
    def test_get_status(self, mock_task_manager):
        """测试获取状态"""
        mock_task = Mock(spec=Task)
        mock_task.task_id = 'test_task'
        mock_task_manager.tasks = deque([mock_task])
        
        # 设置客户端管理器
        mock_client_manager = Mock()
        mock_client_manager.current = Mock()
        mock_client_manager.current.name = 'test_client'
        mock_client_manager.current.model = 'test_model'
        mock_task_manager.client_manager = mock_client_manager
        
        # 模拟 get_status 方法
        mock_task_manager.get_status = Mock(return_value={
            'tasks': 1,
            'current_task': 'test_task',
            'client': 'test_client',
            'model': 'test_model'
        })
        
        status = mock_task_manager.get_status()
        
        assert status['tasks'] == 1
        assert status['current_task'] == 'test_task'
        assert status['client'] == 'test_client'
        assert status['model'] == 'test_model'
        
    @pytest.mark.unit
    def test_get_status_no_current_client(self, mock_task_manager):
        """测试无当前客户端时的状态"""
        mock_task_manager.tasks = deque()
        
        # 设置客户端管理器
        mock_client_manager = Mock()
        mock_client_manager.current = None
        mock_task_manager.client_manager = mock_client_manager
        
        # 模拟 get_status 方法
        mock_task_manager.get_status = Mock(return_value={
            'tasks': 0,
            'current_task': None,
            'client': None,
            'model': None
        })
        
        status = mock_task_manager.get_status()
        
        assert status['tasks'] == 0
        assert status['current_task'] is None
        assert status['client'] is None
        assert status['model'] is None


class TestTaskContext:
    """测试 TaskContext 数据类"""
    
    @pytest.mark.unit
    def test_task_context_creation(self):
        """测试 TaskContext 创建"""
        mock_settings = {'key': 'value'}
        mock_cwd = Path('/test/path')
        mock_plugin_mgr = Mock()
        mock_display_mgr = Mock()
        mock_client_mgr = Mock()
        mock_role_mgr = Mock()
        mock_diagnose = Mock()
        mock_mcp = Mock()
        mock_prompts = Mock()
        
        context = TaskContext(
            settings=mock_settings,
            cwd=mock_cwd,
            plugin_manager=mock_plugin_mgr,
            display_manager=mock_display_mgr,
            client_manager=mock_client_mgr,
            role_manager=mock_role_mgr,
            diagnose=mock_diagnose,
            mcp=mock_mcp,
            prompts=mock_prompts
        )
        
        assert context.settings == mock_settings
        assert context.cwd == mock_cwd
        assert context.plugin_manager == mock_plugin_mgr
        assert context.display_manager == mock_display_mgr
        assert context.client_manager == mock_client_mgr
        assert context.role_manager == mock_role_mgr
        assert context.diagnose == mock_diagnose
        assert context.mcp == mock_mcp
        assert context.prompts == mock_prompts


class TestTaskManagerCleanup:
    """测试 TaskManager 清理功能"""
    
    @pytest.mark.unit
    def test_cleanup_old_tasks(self, mock_task_manager):
        """测试清理旧任务"""
        # 创建超过最大限制的任务
        tasks = []
        for i in range(20):
            task = Mock(spec=Task, task_id=f'task_{i}')
            tasks.append(task)
            
        mock_task_manager.tasks = deque(tasks, maxlen=TaskManager.MAX_TASKS)
        
        # 验证只保留最新的 MAX_TASKS 个任务
        assert len(mock_task_manager.tasks) == TaskManager.MAX_TASKS
        # 最旧的任务应该被移除
        assert mock_task_manager.tasks[0].task_id == 'task_4'
        assert mock_task_manager.tasks[-1].task_id == 'task_19'