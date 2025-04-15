#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import traceback
import importlib.util
from typing import Callable, Any, Dict, List

class EventBus:
    def __init__(self):
        self._listeners: Dict[str, List[Callable[..., Any]]] = {}

    def register(self, event_name: str, handler: Callable[..., Any]):
        self._listeners.setdefault(event_name, []).append(handler)

    def broadcast(self, event_name: str, *args, **kwargs):
        for handler in self._listeners.get(event_name, []):
            try:
                handler(*args, **kwargs)
            except Exception as e:
                traceback.print_exc()

    def pipeline(self, event_name: str, data, **kwargs):
        for handler in self._listeners.get(event_name, []):
            try:
                data = handler(data, **kwargs)
            except Exception as e:
                traceback.print_exc()
        return data

    def collect(self, event_name: str, *args, **kwargs):
        try:
            ret = [handler(*args, **kwargs) for handler in self._listeners.get(event_name, [])]
        except Exception as e:
            ret = []
            traceback.print_exc()
        return ret

    def __call__(self, event_name: str, *args, **kwargs):
        return self.pipeline(event_name, *args, **kwargs)

event_bus = EventBus()

class PluginManager:
    def __init__(self, plugin_dir: str):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Any] = {}

    def load_plugins(self):
        """加载目录下的所有插件文件"""
        if not os.path.exists(self.plugin_dir):
            return

        for fname in os.listdir(self.plugin_dir):
            if fname.endswith(".py") and not fname.startswith("_"):
                self._load_plugin(os.path.join(self.plugin_dir, fname))

    def _load_plugin(self, filepath: str):
        plugin_id = os.path.basename(filepath)[:-3]

        spec = importlib.util.spec_from_file_location(plugin_id, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        plugin_cls = getattr(module, "Plugin", None)
        if not plugin_cls or not callable(plugin_cls):
            print(f"[miniplug] {plugin_id} skipped: no Plugin class.")
            return

        plugin = plugin_cls()

        # 自动注册插件的 on_xxx 方法到 event_bus
        for attr_name in dir(plugin):
            if attr_name.startswith("on_"):
                handler = getattr(plugin, attr_name)
                if callable(handler):
                    event_bus.register(attr_name, handler)

        self.plugins[plugin_id] = plugin
        print(f"[miniplug] Loaded: {plugin_id}")
