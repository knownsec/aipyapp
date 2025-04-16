#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import subprocess
from functools import wraps

from rich.panel import Panel

from .i18n import T
from .templates import DISCLAIMER_TEXT

def restore_output(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__

        try:
            return func(self, *args, **kwargs)
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
    return wrapper

def confirm(console, prompt, default="n", auto=None):
    if auto in (True, False):
        console.print(f"✅ {T('auto_confirm')}")
        return auto
    while True:
        response = console.input(prompt).strip().lower()
        if not response:
            response = default
        if response in ["y", "n"]:
            break
    return response == "y"

def install_packages(console, packages):
    console.print(f"[green]Install packages: {', '.join(packages)} with pip (using Aliyun mirror)")
    pip_cmd = [
        sys.executable, 
        "-m", 
        "pip", 
        "install",
        "-i", 
        "https://mirrors.aliyun.com/pypi/simple/", 
        "--trusted-host", 
        "mirrors.aliyun.com"
    ] + packages
    cp = subprocess.run(pip_cmd)
    return cp.returncode == 0

def confirm_disclaimer(console):
    console.print()
    panel = Panel.fit(DISCLAIMER_TEXT, title="[red]免责声明", border_style="red", padding=(1, 2))
    console.print(panel)

    while True:
        console.print("\n[red]是否确认已阅读并接受以上免责声明？[/red](yes/no):", end=" ")
        response = input().strip().lower()
        if response in ("yes", "y"):
            console.print("[green]感谢确认，程序继续运行。[/green]")
            return True
        elif response in ("no", "n"):
            console.print("[red]您未接受免责声明，程序将退出。[/red]")
            return False
        else:
            console.print("[yellow]请输入 yes 或 no。[/yellow]")

def get_safe_filename(input_str, extension=".html", max_length=16):
    input_str = input_str.strip()
    safe_str = re.sub(r'[\\/:*?"<>|]', '', input_str).strip()
    if not safe_str:
        return None

    name = safe_str[:max_length]
    base_name = name
    filename = f"{base_name}{extension}"
    counter = 1

    while os.path.exists(filename):
        filename = f"{base_name}_{counter}{extension}"
        counter += 1

    return filename
