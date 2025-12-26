from __future__ import annotations
from typing import Dict, Optional


class PromptFeatures:
    """
    灵活的功能开关管理类，支持任意字符串功能名称
    """
    def __init__(self, features: Optional[Dict[str, bool]] = None):
        self.features = {}
        if features:
            self.features.update(features)

    @property
    def enabled_features(self) -> List[str]:
        """返回所有启用的功能"""
        return [k for k, v in self.features.items() if v]
    
    def has(self, *feature_names: str) -> bool:
        """检查功能是否存在且为true"""
        return all(self.features.get(feature_name, False) for feature_name in feature_names)

    def enabled(self, feature_name: str) -> bool:
        """has的别名"""
        return self.has(feature_name)

    def get(self, feature_name: str, default: bool = False) -> bool:
        """获取功能值，支持默认值"""
        return self.features.get(feature_name, default)

    def set(self, feature_name: str, value: bool):
        """设置功能值"""
        self.features[feature_name] = value

    def enable(self, feature_name: str):
        """设置功能值"""
        self.features[feature_name] = True

    def disable(self, feature_name: str):
        """设置功能值为False"""
        self.features[feature_name] = False

    def update(self, features: Dict[str, bool]):
        """批量更新功能"""
        self.features.update(features)

    def to_dict(self) -> Dict[str, bool]:
        """转换为字典"""
        return self.features.copy()
