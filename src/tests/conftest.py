import pytest
import os
from src.utils.config_loader import ConfigLoader
from src.client import AgentClientFactory
from src.utils.evaluator import Evaluator
from src.utils.logger_config import get_test_run_logger, log_test_summary


# 全局结果收集器
test_results_collector = {}

# 全局日志记录器
session_logger = None


@pytest.fixture(scope="session")
def results_collector():
    """
    全局测试结果收集器
    用于收集所有测试用例的执行结果和指标
    """
    return test_results_collector


@pytest.fixture(scope="session")
def config():
    """
    全局配置 Fixture,整个测试会话只加载一次文件
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
            raise ValueError(f"[X] 未找到配置: agents.{agent_key}")

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
    global session_logger
    
    # 初始化测试运行日志
    session_logger = get_test_run_logger()
    session_logger.info("="*100)
    session_logger.info("开始测试会话")
    session_logger.info("="*100)
    
    judge_key = config.get("judge.api_key")
    judge_model = config.get("judge.model", "gpt-4o")
    
    # 获取 Dify 评估配置
    dify_config = config.get("judge.dify_config")
    
    # 如果没配置 base_url，尝试使用全局默认
    if dify_config and "base_url" not in dify_config:
         default_url = config.get("defaults.dify_base_url")
         if default_url:
             dify_config["base_url"] = default_url

    if not judge_key and not dify_config:
        session_logger.warning("未配置 judge.api_key 或 judge.dify_config，仅支持硬规则校验 (hard_check)")
        print("\n[!] Warning: 未配置 judge.api_key 或 judge.dify_config，仅支持硬规则校验 (hard_check)。")
    
    session_logger.info(f"评估器配置: judge_model={judge_model}, dify_config={'已配置' if dify_config else '未配置'}")

    # 始终返回实例，而不是 None
    return Evaluator(judge_api_key=judge_key, model=judge_model, dify_config=dify_config)


def pytest_sessionfinish(session, exitstatus):
    """
    测试会话结束时的钩子函数
    用于保存测试结果到baseline
    """
    from src.utils.baseline_manager import BaselineManager
    import json
    from datetime import datetime
    
    global session_logger
    
    # 记录测试汇总
    if session_logger and test_results_collector:
        log_test_summary(session_logger, test_results_collector)
    
    # 如果设置了环境变量，保存为baseline
    if os.environ.get("SAVE_BASELINE"):
        version_name = os.environ.get("BASELINE_VERSION", "baseline")
        
        if test_results_collector:
            manager = BaselineManager()
            
            # 获取配置元数据
            try:
                config = ConfigLoader("config/config.yaml")
                metadata = {
                    "model": config.get("judge.model", "unknown"),
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat(),
                    "description": os.environ.get("BASELINE_DESCRIPTION", "")
                }
            except:
                metadata = {
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat()
                }
            
            manager.save_baseline(
                version_name=version_name,
                results=test_results_collector,
                metadata=metadata
            )
            if session_logger:
                session_logger.info(f"测试结果已保存为 baseline: {version_name}")
            print(f"\n[OK] 测试结果已保存为 baseline: {version_name}")
    
    # 如果设置了对比baseline
    if os.environ.get("COMPARE_BASELINE"):
        baseline_version = os.environ.get("COMPARE_BASELINE")
        
        if baseline_version and test_results_collector:
            from src.utils.baseline_manager import BaselineManager
            
            manager = BaselineManager()
            
            # 获取当前配置元数据
            try:
                config = ConfigLoader("config/config.yaml")
                current_metadata = {
                    "model": config.get("judge.model", "unknown"),
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat()
                }
            except:
                current_metadata = {
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat()
                }
            
            # 执行对比
            comparison = manager.compare_with_baseline(
                current_results=test_results_collector,
                baseline_version=baseline_version,
                metadata=current_metadata
            )
            
            # 生成对比报告
            if comparison.get("success", True):
                report_path = f"reports/comparison_{baseline_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                manager.generate_comparison_report(comparison, report_path)
                if session_logger:
                    session_logger.info(f"对比报告已生成: {report_path}")
                print(f"\n[*] 对比报告已生成: {report_path}")
    
    # 结束日志
    if session_logger:
        session_logger.info("="*100)
        session_logger.info("测试会话结束")
        session_logger.info("="*100)
