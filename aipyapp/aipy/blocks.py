#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
from pathlib import Path
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Dict, Any

from loguru import logger

from .libmcp import extract_call_tool

@dataclass
class CodeBlock:
    """代码块对象"""
    id: str
    lang: str
    code: str
    path: Optional[str] = None

    def save(self, task_dir: Optional[str] = None):
        """保存代码块到文件，可选传入任务目录前缀"""
        if not self.path:
            return False
        path = Path(self.path)
        # 如果是相对路径且有task_dir，则加上前缀
        if not path.is_absolute() and task_dir:
            path = Path(task_dir) / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.code, encoding='utf-8')
        return True

    @property
    def abs_path(self):
        if self.path:
            return Path(self.path).absolute()
        return None
    
    def get_lang(self):
        lang = self.lang.lower()
        return lang
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'lang': self.lang,
            'code': self.code,
            'path': self.path,
        }

    def __repr__(self):
        return f"<CodeBlock id={self.id}, lang={self.lang}, path={self.path}>"

class CodeBlocks:
    def __init__(self, console):
        self.console = console
        self.blocks = OrderedDict()
        self.code_pattern = re.compile(
            r'<!--\s*Block-Start:\s*(\{.*?\})\s*-->\s*```(\w+)?\s*\n(.*?)\n```\s*<!--\s*Block-End:\s*(\{.*?\})\s*-->',
            re.DOTALL
        )
        self.line_pattern = re.compile(
            r'<!--\s*Cmd-(\w+):\s*(\{.*?\})\s*-->'
        )
        self.log = logger.bind(src='code_blocks')

    def parse(self, markdown_text, parse_mcp=False):
        blocks = OrderedDict()
        errors = []
        for match in self.code_pattern.finditer(markdown_text):
            start_json, lang, content, end_json = match.groups()
            try:
                start_meta = json.loads(start_json)
                end_meta = json.loads(end_json)
            except json.JSONDecodeError as e:
                self.console.print_exception(show_locals=True)
                error = {'JSONDecodeError': {'json_str': start_json, 'reason': str(e)}}
                errors.append(error)
                continue

            code_id = start_meta.get("id")
            if code_id != end_meta.get("id"):
                self.log.error("Start and end id mismatch", start_id=code_id, end_id=end_meta.get("id"))
                error = {'Start and end id mismatch': {'start_id': code_id, 'end_id': end_meta.get("id")}}
                errors.append(error)
                continue

            if code_id in blocks or code_id in self.blocks:
                self.log.error("Duplicate code id", code_id=code_id)
                error = {'Duplicate code id': {'code_id': code_id}}
                errors.append(error)
                continue

            # 创建代码块对象
            block = CodeBlock(
                id=code_id,
                lang=lang,
                code=content,
                path=start_meta.get('path')
            )
            
            blocks[code_id] = block
            self.log.info("Parsed code block", code_block=block)

        self.blocks.update(blocks)

        exec_blocks = []
        line_matches = self.line_pattern.findall(markdown_text)
        for line_match in line_matches:
            cmd, json_str = line_match
            try:
                line_meta = json.loads(json_str)
            except json.JSONDecodeError as e:
                self.log.error("Invalid JSON in Cmd-{cmd} block", json_str=json_str, reason=e)
                error = {f'Invalid JSON in Cmd-{cmd} block': {'json_str': json_str, 'reason': str(e)}}
                errors.append(error)
                continue

            error = None
            if cmd == 'Exec':
                exec_id = line_meta.get("id")
                if not exec_id:
                    error = {'Cmd-Exec block without id': {'json_str': json_str}}
                elif exec_id not in self.blocks:
                    error = {'Cmd-Exec block not found': {'exec_id': exec_id}}
                else:
                    exec_blocks.append(self.blocks[exec_id])
            else:
                error = {f'Unknown command in Cmd-{cmd} block': {'cmd': cmd}}

            if error:
                errors.append(error)

        ret = {}
        if errors: ret['errors'] = errors
        if exec_blocks: ret['exec_blocks'] = exec_blocks
        if blocks: ret['blocks'] = [v for v in blocks.values()]
        
        if parse_mcp and not blocks:
            json_content = extract_call_tool(markdown_text)
            if json_content:
                ret['call_tool'] = json_content
                self.log.info("Parsed MCP call_tool", json_content=json_content)

        return ret
    
    def get_code_by_id(self, code_id):
        try:
            return self.blocks[code_id].code
        except KeyError:
            self.log.error("Code id not found", code_id=code_id)
            self.console.print("❌ Code id not found", code_id=code_id)
            return None
        
    def get_block_by_id(self, code_id):
        try:
            return self.blocks[code_id]
        except KeyError:
            self.log.error("Code id not found", code_id=code_id)
            self.console.print("❌ Code id not found", code_id=code_id)
            return None

    def to_list(self):
        """将 CodeBlocks 对象转换为 JSON 字符串
        
        Returns:
            str: JSON 格式的字符串
        """
        blocks = [block.to_dict() for block in self.blocks.values()]
        return blocks