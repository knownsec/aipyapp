#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Implement interface compatible with aipy/runtime.py, supporting module-level method calls """
import os

def install_packages(*packages):
    print(f"[install_packages] Packages to install: {packages}")
    return True

def get_env(name, default=None, *, desc=None):
    return os.environ.get(name, default)

def display(path=None, url=None):
    if path:
        print(f"[display] Display local file: {path}")
    elif url:
        print(f"[display] Display network resource: {url}")
    else:
        print("[display] No path or url provided")

def input(prompt=''):
    return __builtins__.input(prompt)

def get_block_by_name(block_name):
    pass
