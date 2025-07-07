#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys

def log_debug(msg):
    """写入调试日志"""
    log_path = os.path.expanduser("~/Desktop/aipyapp_debug.log")
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f"{msg}\n")

# 记录启动信息
log_debug(f"启动时间: {__import__('datetime').datetime.now()}")
log_debug(f"Python executable: {sys.executable}")
log_debug(f"Python path: {sys.path}")
log_debug(f"Current directory: {os.getcwd()}")

try:
    from aipyapp.__main__ import mainw
    mainw()
except Exception as e:
    import traceback
    log_debug(f"Error: {e}")
    log_debug(traceback.format_exc())
