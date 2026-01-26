import pytest
from src.utils.config_loader import ConfigLoader
from src.client import AgentClientFactory
from src.utils.evaluator import Evaluator


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
        # 1. 获取该智能体的专属配置
        agent_conf = config.get(f"agents.{agent_key}")
        if not agent_conf:
            raise ValueError(f"❌ 未找到配置: agents.{agent_key}")

        # 2. 【配置融合逻辑】处理 Dify 的公共 base_url
        # 如果是 Dify 平台且没单独配 URL，就用全局默认的
        if agent_conf.get("platform") == "dify":
            if "base_url" not in agent_conf:
                default_url = config.get("defaults.dify_base_url")
                if default_url:
                    agent_conf["base_url"] = default_url

        # 3. 把整个字典丢给工厂，工厂自己去分发
        return AgentClientFactory.create(agent_conf)

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