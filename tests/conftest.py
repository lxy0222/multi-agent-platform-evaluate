import pytest
from utils.dify_client import DifyClient
from utils.config_loader import ConfigLoader
from utils.evaluator import Evaluator

@pytest.fixture(scope="session")
def config():
    """
    全局配置 Fixture，整个测试会话只加载一次文件
    """
    return ConfigLoader("config/config.yaml")


@pytest.fixture(scope="session")
def client_factory(config):
    """
    智能体客户端工厂
    用法: client = client_factory("todo_exec_first")
    """

    def _create_client(agent_key):
        # 1. 从配置文件查找对应的 Agent 配置
        agent_conf = config.get(f"agents.{agent_key}")
        if not agent_conf:
            raise ValueError(f"未在 config.yaml 中找到智能体配置: {agent_key}")

        api_key = agent_conf.get("api_key")
        base_url = config.get("base_url")

        # 2. 返回配置好 Key 的客户端实例
        return DifyClient(api_key=api_key, base_url=base_url)

    return _create_client


@pytest.fixture(scope="session")
def evaluator(config):
    """
    初始化评估器
    即使没有配置 judge key，也返回实例，以便使用 hard_check
    """
    judge_key = config.get("judge.api_key")
    judge_model = config.get("judge.model", "gpt-4o")

    if not judge_key:
        print("\n⚠️ Warning: 未配置 judge.api_key，仅支持硬规则校验 (hard_check)，不支持 LLM 打分。")

    # 始终返回实例，而不是 None
    return Evaluator(judge_api_key=judge_key, model=judge_model)