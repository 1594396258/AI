# Author:HankQueen
# Date:2026/9/17
import yaml
import os


def load_yaml(file_path: str) -> list:
    """
    读取 yaml 文件，返回列表（取决于yaml文件是-开头，表示列表）
    """
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(env: str = "test") -> dict:
    """
    读取 config.yaml，返回指定环境的配置
    """
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "config.yaml"
    )
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config[env]