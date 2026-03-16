import pytest
import os
import logging
from src.utils.config_loader import ConfigLoader
from src.client import AgentClientFactory
from src.utils.medical_evaluator import create_evaluator
from src.utils.logger_config import get_test_run_logger, log_test_summary

# ========================================
# 启用详细的 DEBUG 日志（用于诊断问题）
# ========================================
# 取消下面这行注释以启用 evaluator 的 DEBUG 日志
# logging.getLogger("evaluator").setLevel(logging.DEBUG)

# 或者取消下面这行以启用所有模块的 DEBUG 日志
# logging.basicConfig(level=logging.DEBUG)
# ========================================


# 全局结果收集器
test_results_collector = {}

# 全局日志记录器
session_logger = None


def _group_results_by_agent(results: dict) -> dict:
    grouped = {}
    for case_id, result in results.items():
        agent_key = result.get("target_agent") or "unknown"
        grouped.setdefault(agent_key, {})[case_id] = result
    return grouped


def _get_baseline_config(config: ConfigLoader) -> dict:
    baseline_conf = config.get("baseline", {}) or {}
    per_agent = bool(baseline_conf.get("per_agent", False))
    mapping = baseline_conf.get("by_agent", {}) or {}
    default_baseline = baseline_conf.get("default", "baseline")
    return {
        "per_agent": per_agent,
        "mapping": mapping if isinstance(mapping, dict) else {},
        "default_baseline": default_baseline
    }


def _resolve_baseline_version(agent_key: str, baseline_conf: dict) -> str:
    mapping = baseline_conf.get("mapping", {})
    default_baseline = baseline_conf.get("default_baseline", "baseline")
    if isinstance(mapping, dict) and mapping.get(agent_key):
        return mapping[agent_key]
    return f"{default_baseline}_{agent_key}"


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

    # 使用医疗场景专用评估器
    return create_evaluator(config=config)


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
    
    # 读取 baseline 配置
    baseline_conf = None
    config = None
    try:
        config = ConfigLoader("config/config.yaml")
        baseline_conf = _get_baseline_config(config)
    except Exception:
        baseline_conf = {"per_agent": False, "mapping": {}, "default_baseline": "baseline"}

    # 如果设置了环境变量，保存为baseline
    if os.environ.get("SAVE_BASELINE"):
        version_name = os.environ.get("BASELINE_VERSION") or baseline_conf.get("default_baseline", "baseline")
        
        if test_results_collector:
            manager = BaselineManager()
            
            # 获取配置元数据
            try:
                if not config:
                    raise RuntimeError("config not loaded")
                metadata = {
                    "model": config.get("judge.model", "unknown"),
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat(),
                    "description": os.environ.get("BASELINE_DESCRIPTION", "")
                }
            except Exception:
                metadata = {
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat()
                }
            
            auto_mode = False
            if baseline_conf.get("per_agent", False):
                if str(version_name).lower() in ["auto", "by_agent"]:
                    auto_mode = True
                elif version_name == baseline_conf.get("default_baseline", "baseline"):
                    auto_mode = True

            if auto_mode:
                grouped_results = _group_results_by_agent(test_results_collector)
                for agent_key, agent_results in grouped_results.items():
                    if not agent_results:
                        continue
                    agent_version = _resolve_baseline_version(agent_key, baseline_conf)
                    agent_metadata = dict(metadata)
                    agent_metadata["agent"] = agent_key
                    agent_metadata["test_count"] = len(agent_results)
                    manager.save_baseline(
                        version_name=agent_version,
                        results=agent_results,
                        metadata=agent_metadata
                    )
                    if session_logger:
                        session_logger.info(f"测试结果已保存为 baseline: {agent_version} (agent={agent_key})")
                    print(f"\n[OK] 测试结果已保存为 baseline: {agent_version} (agent={agent_key})")
            else:
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
                if not config:
                    raise RuntimeError("config not loaded")
                current_metadata = {
                    "model": config.get("judge.model", "unknown"),
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat()
                }
            except Exception:
                current_metadata = {
                    "test_count": len(test_results_collector),
                    "timestamp": datetime.now().isoformat()
                }
            
            auto_mode = False
            if baseline_conf.get("per_agent", False):
                if str(baseline_version).lower() in ["auto", "by_agent"]:
                    auto_mode = True
                elif baseline_version == baseline_conf.get("default_baseline", "baseline"):
                    auto_mode = True

            if auto_mode:
                grouped_results = _group_results_by_agent(test_results_collector)
                for agent_key, agent_results in grouped_results.items():
                    if not agent_results:
                        continue
                    agent_version = _resolve_baseline_version(agent_key, baseline_conf)
                    agent_metadata = dict(current_metadata)
                    agent_metadata["agent"] = agent_key
                    agent_metadata["test_count"] = len(agent_results)
                    comparison = manager.compare_with_baseline(
                        current_results=agent_results,
                        baseline_version=agent_version,
                        metadata=agent_metadata
                    )
                    if comparison.get("success", True):
                        report_path = (
                            f"reports/comparison_{agent_version}_{agent_key}_"
                            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                        )
                        manager.generate_comparison_report(comparison, report_path)
                        if session_logger:
                            session_logger.info(f"对比报告已生成: {report_path}")
                        print(f"\n[*] 对比报告已生成: {report_path}")
            else:
                # 执行对比
                comparison = manager.compare_with_baseline(
                    current_results=test_results_collector,
                    baseline_version=baseline_version,
                    metadata=current_metadata
                )
                
                # 生成增强版对比报告
                if comparison.get("success", True):
                    from src.utils.comparison_reporter import ComparisonReporter
                    
                    # 创建增强版报告生成器
                    reporter = ComparisonReporter(comparison)
                    report_path = f"reports/comparison_{baseline_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                    reporter.generate_markdown_report(report_path)
                    
                    if session_logger:
                        session_logger.info(f"增强版对比报告已生成: {report_path}")
                    print(f"\n[*] 增强版对比报告已生成: {report_path}")
    
    # 结束日志
    if session_logger:
        session_logger.info("="*100)
        session_logger.info("测试会话结束")
        session_logger.info("="*100)
