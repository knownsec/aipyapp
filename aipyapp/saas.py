#!/usr/bin/env python
# -*- coding: utf-8 -*-
from enum import Enum, auto
from pathlib import Path
import importlib.resources as resources

from rich.console import Console
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.completion import WordCompleter

from . import __version__
from .aipy import TaskManager
from .aipy.i18n import T, set_lang
from .aipy.config import ConfigManager

__PACKAGE_NAME__ = "aipyapp"

class CommandType(Enum):
    CMD_DONE = auto()
    CMD_USE = auto()
    CMD_EXIT = auto()
    CMD_INVALID = auto()
    CMD_TEXT = auto()
    CMD_LIST = auto()

def parse_command(input_str, llms=set()):
    lower = input_str.lower()

    if lower in ("/done", "done"):
        return CommandType.CMD_DONE, None
    if lower in ("/exit", "exit"):
        return CommandType.CMD_EXIT, None
    if lower in ("/list_llm", "list_llm"):
        return CommandType.CMD_LIST, None
    if lower in llms:
        return CommandType.CMD_USE, input_str
    
    if lower.startswith("/use "):
        arg = input_str[5:].strip()
        if arg in llms:
            return CommandType.CMD_USE, arg
        else:
            return CommandType.CMD_INVALID, arg

    if lower.startswith("use "):
        arg = input_str[4:].strip()
        if arg in llms:
            return CommandType.CMD_USE, arg
               
    return CommandType.CMD_TEXT, input_str

class InteractiveConsole():
    def __init__(self, tm, console, settings):
        self.tm = tm
        self.names = tm.llm.names
        completer = WordCompleter(['/use', 'use', '/done', 'done', '/list_llm', 'list_llm'] + list(self.names['enabled']), ignore_case=True)
        self.history = FileHistory(str(Path.cwd() / settings.history))
        self.session = PromptSession(history=self.history, completer=completer)
        self.console = console
        self.style_main = Style.from_dict({"prompt": "green"})
        self.style_ai = Style.from_dict({"prompt": "cyan"})
        
    def input_with_possible_multiline(self, prompt_text, is_ai=False):
        prompt_style = self.style_ai if is_ai else self.style_main

        first_line = self.session.prompt([("class:prompt", prompt_text)], style=prompt_style)
        if not first_line.endswith("\\"):
            return first_line
        # Multi-line input
        lines = [first_line.rstrip("\\")]
        while True:
            next_line = self.session.prompt([("class:prompt", "... ")], style=prompt_style)
            if next_line.endswith("\\"):
                lines.append(next_line.rstrip("\\"))
            else:
                lines.append(next_line)
                break
        return "\n".join(lines)

    def run_task(self, task, instruction=None):
        try:
            task.run(instruction=instruction)
        except (EOFError, KeyboardInterrupt):
            pass
        except Exception as e:
            self.console.print_exception()

    def start_task_mode(self, task):
        self.console.print(f"{T('ai_mode_enter')}", style="cyan")
        self.run_task(task)
        while True:
            try:
                user_input = self.input_with_possible_multiline(">>> ", is_ai=True).strip()
                if len(user_input) < 2: continue
            except (EOFError, KeyboardInterrupt):
                break

            cmd, arg = parse_command(user_input, self.names['enabled'])
            if cmd == CommandType.CMD_TEXT:
                self.run_task(task, arg)
            elif cmd == CommandType.CMD_DONE:
                break
            elif cmd == CommandType.CMD_USE:
                ret = self.tm.llm.use(arg)
                self.console.print('[green]Ok[/green]' if ret else '[red]Error[/red]')
            elif cmd == CommandType.CMD_INVALID:
                self.console.print(f'[red]Error: {arg}[/red]')

        try:
            task.done()
        except Exception as e:
            self.console.print_exception()
        self.console.print(f"{T('ai_mode_exit')}", style="cyan")

    def run(self):
        self.console.print(f"{T('banner1')}", style="green")
        self.console.print(f"[cyan]{T('default')}: [green]{self.names['default']}，[cyan]{T('enabled')}: [yellow]{' '.join(self.names['enabled'])}")
        while True:
            try:
                user_input = self.input_with_possible_multiline(">> ").strip()
                if len(user_input) < 2:
                    continue

                cmd, arg = parse_command(user_input, self.names['enabled'])
                if cmd == CommandType.CMD_TEXT:
                    task = self.tm.new_task(arg)
                    self.start_task_mode(task)
                elif cmd == CommandType.CMD_USE:
                    ret = self.tm.llm.use(arg)
                    self.console.print('[green]Ok[/green]' if ret else '[red]Error[/red]')
                elif cmd == CommandType.CMD_LIST:
                    self.console.print(f"[cyan]{T('enabled')}: [yellow]{' '.join(self.names['enabled'])}")
                elif cmd == CommandType.CMD_INVALID:
                    self.console.print('[red]Error[/red]')
                elif cmd == CommandType.CMD_EXIT:
                    break
            except (EOFError, KeyboardInterrupt):
                break

def main(args):
    console = Console(record=True)
    console.print(f"[bold cyan]🚀 Python use - AIPython ({__version__}) [[green]https://aipy.app[/green]]")
    
    path = args.config if args.config else 'aipy.toml'
    default_config_path = resources.files(__PACKAGE_NAME__) / "default.toml"
    conf = ConfigManager(default_config_path, path)
    conf.check_config()
    settings = conf.get_config()

    lang = settings.get('lang')
    if lang: set_lang(lang)

    try:
        tm = TaskManager(settings, console=console)
    except Exception as e:
        console.print_exception()
        return
    
    if not tm.llm:
        console.print(f"[bold red]{T('no_available_llm')}")
        return
    
    if args.cmd:
        tm.new_task(args.cmd).run()
        return
    InteractiveConsole(tm, console, settings).run()
