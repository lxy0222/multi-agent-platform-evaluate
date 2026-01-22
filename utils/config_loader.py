import yaml
import os
from typing import Any


class ConfigLoader:
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        初始化配置加载器
        :param config_path: 配置文件相对于项目根目录的路径
        """
        # 获取当前脚本的绝对路径，向上推导找到项目根目录
        # 假设 utils/config_loader.py 在 utils 文件夹下
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)

        self.file_path = os.path.join(project_root, config_path)
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """加载 YAML 文件内容"""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"配置文件未找到: {self.file_path}\n请确保在 config/ 目录下创建了 config.yaml")

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise RuntimeError(f"解析配置文件失败: {str(e)}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        获取配置项，支持点号索引，例如 "dify.api_key"

        :param key_path: 配置键路径，如 "judge.model"
        :param default: 默认值
        :return: 配置值
        """
        keys = key_path.split('.')
        value = self._config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    @property
    def all_config(self):
        """返回完整配置字典"""
        return self._config


# 单例模式测试（可选）
if __name__ == "__main__":
    conf = ConfigLoader()
    print(f"Dify Base URL: {conf.get('dify.base_url')}")