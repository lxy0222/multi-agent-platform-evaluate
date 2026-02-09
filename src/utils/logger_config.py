"""
日志配置模块
提供统一的日志配置和格式化输出
"""
import logging
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（用于控制台）"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
    }
    RESET = '\033[0m'
    
    def format(self, record):
        # 保存原始的 levelname
        original_levelname = record.levelname
        
        # 添加颜色（只修改显示，不修改record本身）
        if original_levelname in self.COLORS:
            # 创建一个副本避免修改原始 record
            colored_levelname = f"{self.COLORS[original_levelname]}{original_levelname}{self.RESET}"
            record.levelname = colored_levelname
        
        # 格式化消息
        result = super().format(record)
        
        # 恢复原始 levelname
        record.levelname = original_levelname
        
        return result


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    enable_console: bool = True,
    enable_file: bool = True,
    log_dir: str = "logs"
) -> logging.Logger:
    """
    创建并配置日志记录器
    
    Args:
        name: 日志记录器名称
        log_file: 日志文件名（如果为None，则使用name）
        level: 日志级别
        enable_console: 是否输出到控制台
        enable_file: 是否输出到文件
        log_dir: 日志文件目录
    
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # 防止日志传播到root logger
    
    # 清除已有的处理器
    logger.handlers.clear()
    
    # 控制台处理器（带颜色）
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = ColoredFormatter(
            fmt='[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 文件处理器（无颜色，详细格式）
    if enable_file:
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # 生成日志文件名
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d")
            log_file = f"{name}_{timestamp}.log"
        
        file_handler = logging.FileHandler(
            log_path / log_file,
            mode='a',
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            fmt='[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取已配置的日志记录器，如果不存在则创建
    
    Args:
        name: 日志记录器名称
    
    Returns:
        日志记录器
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # 如果logger没有处理器，使用默认配置
        setup_logger(name)
    return logger


def get_test_run_logger(run_name: Optional[str] = None) -> logging.Logger:
    """
    获取测试运行专用的日志记录器
    
    Args:
        run_name: 测试运行名称（可选）
    
    Returns:
        日志记录器
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if run_name:
        log_filename = f"test_run_{run_name}_{timestamp}.log"
    else:
        log_filename = f"test_run_{timestamp}.log"
    
    return setup_logger(
        name="test_runner",
        log_file=log_filename,
        level=logging.DEBUG,  # 测试日志使用DEBUG级别
        enable_console=True,
        enable_file=True
    )


class TestCaseLogger:
    """测试用例专用日志记录器（结构化）"""
    
    def __init__(self, case_id: str, logger: Optional[logging.Logger] = None):
        """
        初始化测试用例日志记录器
        
        Args:
            case_id: 测试用例ID
            logger: 父日志记录器（可选）
        """
        self.case_id = case_id
        self.logger = logger or get_logger("test_case")
        self._case_start_time = None
    
    def start(self):
        """记录用例开始"""
        self._case_start_time = datetime.now()
        self.logger.info(f"{'='*80}")
        self.logger.info(f"开始执行测试用例: {self.case_id}")
        self.logger.info(f"{'='*80}")
    
    def log_request(self, request_data: dict):
        """记录请求信息"""
        self.logger.info(f"[{self.case_id}] 发送请求:")
        for key, value in request_data.items():
            self.logger.debug(f"  {key}: {value}")
    
    def log_response(self, response_data: dict):
        """记录响应信息"""
        self.logger.info(f"[{self.case_id}] 收到响应:")
        for key, value in response_data.items():
            if key == "answer" or key == "json_data":
                self.logger.info(f"  {key}: {value}")
            else:
                self.logger.debug(f"  {key}: {value}")
    
    def log_validation(self, validation_result: dict):
        """记录校验结果"""
        passed = validation_result.get("passed", False)
        status = "✅ 通过" if passed else "❌ 失败"
        self.logger.info(f"[{self.case_id}] 硬规则校验: {status}")
        
        if not passed:
            errors = validation_result.get("errors", [])
            for error in errors:
                self.logger.warning(f"  - {error}")
    
    def log_evaluation(self, eval_result: dict):
        """记录LLM评估结果"""
        overall_score = eval_result.get("overall_score", 0)
        overall_reason = eval_result.get("overall_reason", "")
        dimensions = eval_result.get("dimensions", {})
        
        self.logger.info(f"[{self.case_id}] LLM评估结果:")
        self.logger.info(f"  📊 综合评分: {overall_score}/100")
        self.logger.info(f"  💭 评估理由: {overall_reason}")
        
        if dimensions:
            self.logger.info(f"  📋 各维度评分:")
            for dim_name, dim_data in dimensions.items():
                if isinstance(dim_data, dict):
                    score = dim_data.get("score", 0)
                    reason = dim_data.get("reason", "")
                    self.logger.info(f"    - {dim_name}: {score}/100")
                    if reason:
                        self.logger.debug(f"      原因: {reason}")
    
    def log_metrics(self, metrics: dict):
        """记录性能指标"""
        self.logger.info(f"[{self.case_id}] 性能指标:")
        self.logger.info(f"  ⏱️  响应时间: {metrics.get('response_time_ms', 0):.2f}ms")
        self.logger.info(f"  ⏱️  总耗时: {metrics.get('total_duration_ms', 0):.2f}ms")
        
        if metrics.get('is_timeout'):
            self.logger.warning(f"  ⚠️  响应超时")
    
    def finish(self, success: bool, overall_score: float = 0):
        """记录用例结束"""
        duration = (datetime.now() - self._case_start_time).total_seconds() if self._case_start_time else 0
        
        status = "✅ 成功" if success else "❌ 失败"
        self.logger.info(f"[{self.case_id}] 测试结果: {status} | 评分: {overall_score}/100 | 耗时: {duration:.2f}s")
        self.logger.info(f"{'='*80}\n")


def log_test_summary(logger: logging.Logger, results_collector: dict):
    """
    记录测试运行汇总信息
    
    Args:
        logger: 日志记录器
        results_collector: 测试结果收集器
    """
    logger.info("\n" + "="*100)
    logger.info("测试执行汇总")
    logger.info("="*100)
    
    if not results_collector:
        logger.warning("没有收集到测试结果")
        return
    
    total_cases = len(results_collector)
    passed_cases = sum(1 for r in results_collector.values() if r.get("validation_passed", False))
    failed_cases = total_cases - passed_cases
    
    # 计算评分统计
    scores = [r.get("overall_score", 0) for r in results_collector.values()]
    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0
    
    # 计算响应时间统计
    response_times = [r.get("response_time_ms", 0) for r in results_collector.values()]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    logger.info(f"\n📊 基础统计:")
    logger.info(f"  总用例数: {total_cases}")
    logger.info(f"  通过数量: {passed_cases} ({passed_cases/total_cases*100:.1f}%)")
    logger.info(f"  失败数量: {failed_cases} ({failed_cases/total_cases*100:.1f}%)")
    
    logger.info(f"\n📈 评分统计:")
    logger.info(f"  平均分: {avg_score:.2f}")
    logger.info(f"  最高分: {max_score:.2f}")
    logger.info(f"  最低分: {min_score:.2f}")
    
    logger.info(f"\n⏱️  性能统计:")
    logger.info(f"  平均响应时间: {avg_response_time:.2f}ms")
    
    # 按维度统计
    dimension_scores = {}
    for result in results_collector.values():
        dimensions = result.get("dimensions", {})
        for dim_name, dim_data in dimensions.items():
            if isinstance(dim_data, dict):
                score = dim_data.get("score", 0)
                if dim_name not in dimension_scores:
                    dimension_scores[dim_name] = []
                dimension_scores[dim_name].append(score)
    
    if dimension_scores:
        logger.info(f"\n📋 维度平均分:")
        for dim_name, scores in dimension_scores.items():
            avg_dim_score = sum(scores) / len(scores) if scores else 0
            logger.info(f"  {dim_name}: {avg_dim_score:.2f}")
    
    # 列出失败的用例
    if failed_cases > 0:
        logger.info(f"\n❌ 失败用例列表:")
        for case_id, result in results_collector.items():
            if not result.get("validation_passed", False):
                score = result.get("overall_score", 0)
                reason = result.get("overall_reason", "未知原因")
                logger.warning(f"  - {case_id}: 评分={score:.2f}, 原因={reason}")
    
    logger.info("\n" + "="*100 + "\n")
