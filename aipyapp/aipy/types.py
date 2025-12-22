#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Any, Dict, List, Callable, Optional, TypeVar, Iterable, ClassVar
import weakref

from pydantic import BaseModel, Field

class Error(BaseModel):
    """错误"""
    message: str
    context: Dict[str, Any] | None = None

    @classmethod
    def new(cls, message: str, /, **context):
        return cls(message=message, context=context)

    def to_json(self) -> str:
        """获取错误信息"""
        return self.model_dump_json(exclude_none=True, exclude_unset=True)

class Errors(BaseModel):
    """错误列表"""
    errors: List[Error] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.errors)

    def append(self, error: Error):
        self.errors.append(error)

    def add(self, message: str, /, **context):
        self.errors.append(Error(message=message, context=context))

    def extend(self, errors: Errors):
        self.errors.extend(errors.errors)

    def to_json(self) -> str:
        """获取错误信息"""
        # Do NOT use exclude_unset=True here.
        # The `errors` list is often mutated in-place via `add()/append()`, and
        # pydantic may still consider the field "unset" which would serialize to `{}`.
        return self.model_dump_json(exclude_none=True)

T = TypeVar('T')
ItemType = TypeVar('ItemType')

class Traverser:
    """通用遍历器，支持正序和倒序"""

    def __init__(self, items: Iterable[ItemType], reverse: bool = True):
        """
        初始化遍历器

        Args:
            items: 可遍历的容器
            reverse: True为倒序遍历，False为正序遍历，默认倒序
        """
        self.items = items
        self.reverse = reverse

    def iterate(self):
        """根据设置返回相应的迭代器"""
        if self.reverse:
            if hasattr(self.items, '__reversed__') or hasattr(self.items, '__getitem__'):
                return reversed(self.items)
            else:
                # 对于不支持reversed的可迭代对象，先转换为list再反转
                return reversed(list(self.items))
        else:
            return iter(self.items)

    def find_first(self, selector: Callable[[ItemType], Optional[T]]) -> Optional[T]:
        """查找第一个匹配的项"""
        for item in self.iterate():
            result = selector(item)
            if result is not None:
                return result
        return None

    def find_all(self, selector: Callable[[ItemType], list[T]]) -> list[T]:
        """查找所有匹配的项"""
        results = []
        for item in self.iterate():
            items = selector(item)
            results.extend(items)
        return results

    def find_by_condition(self, condition: Callable[[ItemType], bool]) -> Optional[ItemType]:
        """查找第一个满足条件的项"""
        for item in self.iterate():
            if condition(item):
                return item
        return None

    def filter_and_map(self,
                    condition: Callable[[ItemType], bool],
                    mapper: Callable[[ItemType], T]) -> list[T]:
        """过滤并映射"""
        results = []
        for item in self.iterate():
            if condition(item):
                results.append(mapper(item))
        return results

    def with_reverse(self, reverse: bool = True):
        """返回一个新的遍历器，使用指定的遍历方向"""
        return Traverser(self.items, reverse)

    def take(self, count: int) -> list[ItemType]:
        """取前N个元素"""
        result = []
        for i, item in enumerate(self.iterate()):
            if i >= count:
                break
            result.append(item)
        return result

    @property
    def last(self) -> Optional[ItemType]:
        """获取最后一个元素"""
        items = list(self.iterate())
        if items:
            return items[-1]
        return None

    def skip(self, count: int):
        """跳过前N个元素，返回新的遍历器"""
        items = list(self.iterate())[count:]
        return Traverser(items, reverse=False)  # 已经处理过顺序

    def where(self, condition: Callable[[ItemType], bool]):
        """过滤，返回新的遍历器"""
        filtered_items = [item for item in self.iterate() if condition(item)]
        return Traverser(filtered_items, reverse=False)  # 已经处理过顺序
    
class DataMixin:
    __expose__: set = set()

    def __getattr__(self, name):
        if name in self.__expose__:
            return getattr(self._data, name)
        raise AttributeError(name)

    def __dir__(self):
        return list(super().__dir__()) + list(self.__expose__)

class InstanceTrackerMixin:
    # 每个子类会自动拥有自己的 WeakSet
    __instances__: ClassVar[weakref.WeakSet] = weakref.WeakSet()

    def model_post_init(self, __context):
        # 只把该具体子类的实例加入自己的池子
        cls = type(self)
        # 每个子类应当有自己独立的 WeakSet，而不是共用父类的
        if "__instances__" not in cls.__dict__:
            cls.__instances__ = weakref.WeakSet()
        cls.__instances__.add(self)

    @classmethod
    def all_instances(cls):
        if "__instances__" not in cls.__dict__:
            return []
        return list(cls.__instances__)
