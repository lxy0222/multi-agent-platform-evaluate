"""
Baseline 管理模块
用于保存、加载和对比不同版本的测试结果
支持模型/Prompt调优效果评估
"""
import json
import os
import yaml
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class BaselineManager:
    """Baseline 数据管理器"""

    def __init__(self, baseline_dir: str = "data/baselines", metrics_config: str = "src/config/evaluation_metrics.yaml"):
        """
        初始化 Baseline 管理器

        Args:
            baseline_dir: baseline 数据存储目录
            metrics_config: 评估维度配置文件路径
        """
        self.baseline_dir = Path(baseline_dir)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)

        # 加载评估维度配置
        self.metrics_config = self._load_metrics_config(metrics_config)

        # 当前运行的结果
        self.current_results: Dict[str, Dict] = {}

    def _load_metrics_config(self, config_path: str) -> Dict:
        """加载评估维度配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"[!] 评估配置文件不存在: {config_path}，使用默认配置")
            return {
                "dimensions": {},
                "comparison_rules": {
                    "improvement_threshold": {"score": 5, "pass_rate": 3},
                    "degradation_threshold": {"score": -5, "pass_rate": -3}
                }
            }

    def save_baseline(
        self,
        version_name: str,
        results: Dict[str, Dict],
        metadata: Optional[Dict] = None
    ) -> str:
        """
        保存当前测试结果为 baseline

        Args:
            version_name: 版本名称，例如 "v1.0_gpt4" 或 "baseline_original"
            results: 测试结果字典，key 为 case_id
            metadata: 额外的元数据（模型配置、prompt版本等）

        Returns:
            保存的文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 增强每个用例，包含硬校验详情
        enhanced_results = {}
        for case_id, case_data in results.items():
            enhanced_results[case_id] = self._add_hard_validation(case_data)

        baseline_data = {
            "version": version_name,
            "timestamp": timestamp,
            "metadata": metadata or {},
            "results": enhanced_results,
            "summary": self._calculate_summary(enhanced_results)
        }

        # 保存两份：一份带时间戳（历史记录），一份最新版本
        timestamped_file = self.baseline_dir / f"{version_name}_{timestamp}.json"
        latest_file = self.baseline_dir / f"{version_name}_latest.json"

        for filepath in [timestamped_file, latest_file]:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(baseline_data, f, ensure_ascii=False, indent=2)

        print(f"[OK] Baseline 已保存: {latest_file}")
        return str(latest_file)

    def _add_hard_validation(self, case_data: Dict) -> Dict:
        """添加硬校验信息到用例数据 - 包含所有检查点详情"""
        if not case_data:
            return {}

        validation = case_data.get("validation", {})
        validation_passed = case_data.get("validation_passed", False)

        # 提取所有检查点的详细信息
        checks = validation.get("checks", [])
        enhanced_checks = []

        for check in checks:
            if isinstance(check, dict):
                enhanced_checks.append({
                    "name": check.get("name", check.get("check_name", check.get("type", ""))),
                    "passed": check.get("passed", check.get("success", False)),
                    "message": check.get("message", check.get("msg", check.get("requirement", ""))),
                    "details": check.get("details", {}),
                    "metadata": check.get("metadata", {})
                })
            elif isinstance(check, str):
                enhanced_checks.append({
                    "name": check,
                    "passed": True,
                    "message": "",
                    "details": {},
                    "metadata": {}
                })

        # 提取错误详情
        errors = validation.get("errors", [])
        enhanced_errors = []

        for error in errors:
            if isinstance(error, dict):
                enhanced_errors.append({
                    "check_name": error.get("check_name", error.get("name", "")),
                    "error_message": error.get("error_message", error.get("message", "")),
                    "expected": error.get("expected"),
                    "actual": error.get("actual"),
                    "severity": error.get("severity", "error")
                })
            elif isinstance(error, str):
                enhanced_errors.append({
                    "check_name": "",
                    "error_message": error,
                    "expected": None,
                    "actual": None,
                    "severity": "error"
                })

        # 构建精简的 hard_validation 结构
        hard_validation = {
            "passed": validation_passed,
            "total_checks": len(enhanced_checks),
            "passed_checks": sum(1 for c in enhanced_checks if c.get("passed", False)),
            "failed_checks": sum(1 for c in enhanced_checks if not c.get("passed", False)),
            "checks": enhanced_checks,
            "errors": enhanced_errors
        }

        # 返回精简后的用例数据，移除重复字段
        cleaned_data = {
            "case_id": case_data.get("case_id", ""),
            "target_agent": case_data.get("target_agent", ""),
            "scene_description": case_data.get("scene_description", ""),
            "validation_passed": validation_passed,  # 保留顶层布尔值便于快速筛选
            "hard_score": case_data.get("hard_score", 0),
            "soft_score": case_data.get("soft_score"),
            "soft_evaluated": case_data.get("soft_evaluated", False),
            "soft_pass": case_data.get("soft_pass"),
            "judge_soft_pass": case_data.get("judge_soft_pass"),
            "min_score_threshold": case_data.get("min_score_threshold", 75),
            "overall_score": case_data.get("overall_score", 0),
            "overall_reason": case_data.get("overall_reason", ""),
            "overall_pass": case_data.get("overall_pass", validation_passed),
            "hard_validation": hard_validation,
            "dimensions": self._extract_dimensions(case_data),
            "llm_evaluation": case_data.get("llm_evaluation", {}),
            "metrics": case_data.get("metrics", {}),
            "duration_ms": case_data.get("duration_ms", 0),
            "response_time_ms": case_data.get("response_time_ms", 0),
            "timestamp": case_data.get("timestamp", "")
        }

        return cleaned_data

    def load_baseline(self, version_name: str) -> Optional[Dict]:
        """
        加载指定版本的 baseline

        Args:
            version_name: 版本名称

        Returns:
            baseline 数据，如果不存在则返回 None
        """
        latest_file = self.baseline_dir / f"{version_name}_latest.json"

        if not latest_file.exists():
            print(f"[!] Baseline 不存在: {version_name}")
            return None

        with open(latest_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def compare_with_baseline(
        self,
        current_results: Dict[str, Dict],
        baseline_version: str,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        将当前结果与 baseline 进行对比

        Args:
            current_results: 当前测试结果
            baseline_version: 要对比的 baseline 版本
            metadata: 当前版本的元数据

        Returns:
            对比报告
        """
        baseline = self.load_baseline(baseline_version)

        if not baseline:
            return {
                "success": False,
                "error": f"Baseline '{baseline_version}' not found"
            }

        baseline_results = baseline.get("results", {})

        comparison = {
            "baseline_version": baseline_version,
            "baseline_timestamp": baseline.get("timestamp"),
            "current_timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "baseline_metadata": baseline.get("metadata", {}),
            "current_metadata": metadata or {},
            "case_comparisons": {},
            "summary": {
                "total_cases": 0,
                "baseline_total_cases": len(baseline_results),
                "current_total_cases": 0,
                "comparable_cases": 0,
                "improved": 0,
                "degraded": 0,
                "unchanged": 0,
                "new_cases": 0,
                "missing_cases": 0
            },
            "metrics": {
                "baseline": {},
                "current": {},
                "delta": {}
            }
        }

        # 只对比当前实际运行的用例（而非 baseline 全量）
        # 修复：之前使用 all_case_ids = set(baseline_results.keys()) | set(current_results.keys())
        # 导致显示 baseline 的所有用例，现在只对比 current 中实际运行的用例
        current_case_ids = set(current_results.keys())
        comparable_case_ids = current_case_ids & set(baseline_results.keys())
        baseline_subset = {
            case_id: baseline_results[case_id]
            for case_id in comparable_case_ids
        }
        current_subset = {
            case_id: current_results[case_id]
            for case_id in comparable_case_ids
        }

        # baseline / current 汇总都按本次参与对比的 case 子集重算，
        # 避免报告拿 baseline 全量统计去和本次少量用例做对比。
        comparison["metrics"]["baseline"] = self._calculate_summary(baseline_subset)
        comparison["metrics"]["current"] = self._calculate_summary(current_subset)
        comparison["summary"]["total_cases"] = len(current_case_ids)
        comparison["summary"]["current_total_cases"] = len(current_case_ids)
        comparison["summary"]["comparable_cases"] = len(comparable_case_ids)

        for case_id in current_case_ids:
            baseline_case = baseline_results.get(case_id)
            current_case = current_results.get(case_id)

            case_comparison = self._compare_single_case(
                case_id, baseline_case, current_case
            )

            comparison["case_comparisons"][case_id] = case_comparison

            # 更新统计
            status = case_comparison["status"]
            if status == "improved":
                comparison["summary"]["improved"] += 1
            elif status == "degraded":
                comparison["summary"]["degraded"] += 1
            elif status == "unchanged":
                comparison["summary"]["unchanged"] += 1
            elif status == "new":
                comparison["summary"]["new_cases"] += 1
            elif status == "missing":
                comparison["summary"]["missing_cases"] += 1

        # 计算整体指标变化
        comparison["metrics"]["delta"] = self._calculate_delta(
            comparison["metrics"]["baseline"],
            comparison["metrics"]["current"]
        )

        return comparison

    def _compare_single_case(
        self,
        case_id: str,
        baseline_case: Optional[Dict],
        current_case: Optional[Dict]
    ) -> Dict:
        """对比单个测试用例 - 增强版，包含详细校验信息"""
        if not baseline_case and current_case:
            return {
                "status": "new",
                "case_id": case_id,
                "baseline": None,
                "current": self._extract_case_info(current_case),
                "delta": {}
            }

        if baseline_case and not current_case:
            return {
                "status": "missing",
                "case_id": case_id,
                "baseline": self._extract_case_info(baseline_case),
                "current": None,
                "delta": {}
            }

        # 提取详细信息
        baseline_info = self._extract_case_info(baseline_case)
        current_info = self._extract_case_info(current_case)

        delta = {
            "score": current_info["score"] - baseline_info["score"],
            "score_percent": ((current_info["score"] - baseline_info["score"]) / max(baseline_info["score"], 1)) * 100,
            "duration": current_info["duration_ms"] - baseline_info["duration_ms"],
            "duration_percent": ((current_info["duration_ms"] - baseline_info["duration_ms"]) / max(baseline_info["duration_ms"], 1)) * 100,
            "response_time": current_info["response_time_ms"] - baseline_info["response_time_ms"],
            "response_time_percent": ((current_info["response_time_ms"] - baseline_info["response_time_ms"]) / max(baseline_info["response_time_ms"], 1)) * 100,
            "validation_changed": baseline_info["overall_pass"] != current_info["overall_pass"]
        }

        # 判断状态
        if not baseline_info["overall_pass"] and current_info["overall_pass"]:
            status = "improved"
        elif baseline_info["overall_pass"] and not current_info["overall_pass"]:
            status = "degraded"
        elif delta["score"] > 5:
            status = "improved"
        elif delta["score"] < -5:
            status = "degraded"
        else:
            status = "unchanged"

        return {
            "status": status,
            "case_id": case_id,
            "baseline": baseline_info,
            "current": current_info,
            "delta": delta
        }

    def _extract_case_info(self, case: Dict) -> Dict:
        """提取用例详细信息，包含硬校验和软校验数据"""
        if not case:
            return {}

        llm_dimensions = self._extract_dimensions(case)

        # 硬校验结果
        hard_validation = case.get("hard_validation", {}) or {}
        hard_passed = (
            case.get("validation_passed", False)
            or case.get("success", False)
            or bool(hard_validation.get("passed", False))
        )

        # 软校验结果 - 关键修复：兼容多种数据结构
        llm_eval = case.get("llm_evaluation", {})
        soft_score = case.get("soft_score")
        if soft_score is None:
            if llm_eval and "overall_score" in llm_eval:
                soft_score = llm_eval.get("overall_score")
        llm_reason = llm_eval.get("overall_reason", "") if llm_eval else ""

        # 兼容性处理：也支持扁平结构
        if soft_score is None and "llm_score" in case:
            soft_score = case.get("llm_score", 0)
            llm_reason = case.get("llm_reason", "")

        overall_score = case.get("overall_score")
        if overall_score is None:
            overall_score = soft_score or 0

        overall_reason = case.get("overall_reason") or llm_reason
        overall_pass = self._resolve_overall_pass(case)

        # 硬校验详情
        validation_result = case.get("validation", {}) or {}
        if not validation_result and hard_validation:
            validation_result = hard_validation

        validation_checks = validation_result.get("checks", []) or []
        validation_errors = validation_result.get("errors", []) or []

        # 性能指标
        metrics = case.get("metrics", {})
        duration_ms = metrics.get("total_duration_ms", case.get("duration_ms", 0))
        response_time_ms = metrics.get("response_time_ms", case.get("response_time_ms", 0))

        return {
            "score": overall_score,
            "passed": hard_passed,
            "hard_passed": hard_passed,
            "overall_pass": overall_pass,
            "hard_score": case.get("hard_score", 0),
            "soft_score": soft_score,
            "soft_pass": self._resolve_soft_pass(case),
            "judge_soft_pass": case.get("judge_soft_pass"),
            "soft_evaluated": case.get("soft_evaluated", soft_score is not None),
            "duration_ms": duration_ms,
            "response_time_ms": response_time_ms,
            "reason": overall_reason,
            "llm_score": soft_score,
            "llm_reason": llm_reason,
            "llm_dimensions": llm_dimensions,  # 使用合并后的 dimensions
            "validation_checks": validation_checks,
            "validation_errors": validation_errors,
            "dimensions": llm_dimensions  # 修复：使用 llm_dimensions 而非空的 case.get("dimensions")
        }

    def _calculate_summary(self, results: Dict[str, Dict]) -> Dict:
        """计算测试结果的统计摘要 - 增强版"""
        if not results:
            return self._get_empty_summary()

        total = len(results)
        hard_passed = sum(1 for r in results.values() if r.get("validation_passed", False) or r.get("success", False))
        composite_passed = sum(1 for r in results.values() if self._resolve_overall_pass(r))
        soft_evaluated_cases = sum(1 for r in results.values() if r.get("soft_evaluated", False) or r.get("soft_score") is not None)
        soft_passed = sum(
            1 for r in results.values()
            if (r.get("soft_evaluated", False) or r.get("soft_score") is not None)
            and bool(self._resolve_soft_pass(r))
        )

        # 提取评分 - 优先使用 llm_evaluation.overall_score
        scores = []
        hard_scores = []
        soft_scores = []
        durations = []
        response_times = []

        for r in results.values():
            scores.append(r.get("overall_score", 0) or 0)
            hard_scores.append(r.get("hard_score", 0) or 0)
            if r.get("soft_score") is not None:
                soft_scores.append(r.get("soft_score", 0) or 0)

            # 性能指标提取
            metrics = r.get("metrics", {})
            durations.append(metrics.get("total_duration_ms", r.get("duration_ms", 0)))
            response_times.append(metrics.get("response_time_ms", r.get("response_time_ms", 0)))

        # 计算各维度的平均分
        avg_dimensions = self._calculate_all_dimension_scores(results)

        # 计算核心维度分数
        self._calculate_core_dimension_scores(results, avg_dimensions)

        avg_overall_score = sum(scores) / len(scores) if scores else 0.0
        avg_hard_score = sum(hard_scores) / len(hard_scores) if hard_scores else 0.0
        avg_soft_score = sum(soft_scores) / len(soft_scores) if soft_scores else 0.0
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0

        return {
            "total_cases": total,
            "passed_cases": composite_passed,
            "failed_cases": total - composite_passed,
            "hard_passed_cases": hard_passed,
            "hard_failed_cases": total - hard_passed,
            "soft_evaluated_cases": soft_evaluated_cases,
            "soft_passed_cases": soft_passed,
            "pass_rate": (composite_passed / total * 100) if total > 0 else 0.0,
            "hard_pass_rate": (hard_passed / total * 100) if total > 0 else 0.0,
            "soft_pass_rate": (soft_passed / soft_evaluated_cases * 100) if soft_evaluated_cases > 0 else 0.0,
            "avg_overall_score": avg_overall_score,
            "avg_hard_score": avg_hard_score,
            "avg_soft_score": avg_soft_score,
            "avg_duration_ms": avg_duration,
            "avg_response_time_ms": avg_response_time,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "avg_dimensions": avg_dimensions
        }

    def _get_empty_summary(self) -> Dict:
        """返回空摘要"""
        return {
            "total_cases": 0, "passed_cases": 0, "failed_cases": 0,
            "hard_passed_cases": 0, "hard_failed_cases": 0,
            "soft_evaluated_cases": 0, "soft_passed_cases": 0,
            "pass_rate": 0.0, "hard_pass_rate": 0.0, "soft_pass_rate": 0.0,
            "avg_overall_score": 0.0, "avg_hard_score": 0.0, "avg_soft_score": 0.0,
            "avg_duration_ms": 0.0, "avg_response_time_ms": 0.0,
            "avg_dimensions": {}
        }

    def _extract_dimensions(self, case: Optional[Dict]) -> Dict[str, Any]:
        """兼容读取顶层 dimensions 和 llm_evaluation.dimensions。"""
        if not case:
            return {}

        top_level_dimensions = case.get("dimensions", {})
        if isinstance(top_level_dimensions, dict) and top_level_dimensions:
            return top_level_dimensions

        llm_eval = case.get("llm_evaluation", {}) or {}
        llm_dimensions = llm_eval.get("dimensions", {})
        if isinstance(llm_dimensions, dict) and llm_dimensions:
            return llm_dimensions

        return {}

    def _resolve_soft_pass(self, case: Optional[Dict]) -> Optional[bool]:
        """统一解析软校验是否通过，优先按分数阈值口径。"""
        if not case:
            return None

        explicit_soft_pass = case.get("soft_pass")
        if explicit_soft_pass is not None:
            return bool(explicit_soft_pass)

        soft_score = case.get("soft_score")
        if soft_score is not None:
            threshold = float(case.get("min_score_threshold", 75) or 75)
            return float(soft_score) >= threshold

        llm_eval = case.get("llm_evaluation", {}) or {}
        if "pass" in llm_eval:
            return bool(llm_eval.get("pass"))

        return None

    def _resolve_overall_pass(self, case: Optional[Dict]) -> bool:
        """统一解析最终是否通过，避免历史数据沿用旧的 judge 布尔口径。"""
        if not case:
            return False

        hard_passed = case.get("validation_passed", False) or case.get("success", False)
        soft_evaluated = case.get("soft_evaluated", False) or case.get("soft_score") is not None
        soft_pass = self._resolve_soft_pass(case)
        return hard_passed and (soft_pass if soft_evaluated and soft_pass is not None else True)

    def _calculate_all_dimension_scores(self, results: Dict[str, Dict]) -> Dict[str, float]:
        """计算所有维度的平均分"""
        all_dimensions = {}

        for r in results.values():
            dims = self._extract_dimensions(r)
            if not isinstance(dims, dict):
                continue

            for dim_key, dim_value in dims.items():
                if isinstance(dim_value, dict):
                    if "score" in dim_value and isinstance(dim_value["score"], (int, float)):
                        all_dimensions.setdefault(dim_key, []).append(dim_value["score"])

                    # 嵌套维度结构
                    for sub_key, sub_value in dim_value.items():
                        if sub_key in {"score", "reason", "details", "threshold", "pass", "score_range"}:
                            continue
                        if isinstance(sub_value, dict) and "score" in sub_value:
                            full_key = f"{dim_key}.{sub_key}"
                            all_dimensions.setdefault(full_key, []).append(sub_value["score"])
                elif isinstance(dim_value, (int, float)):
                    all_dimensions.setdefault(dim_key, []).append(dim_value)

        # 计算平均分
        avg_dimensions = {}
        for dim_name, scores_list in all_dimensions.items():
            if scores_list:
                avg_dimensions[dim_name] = round(sum(scores_list) / len(scores_list), 2)

        return avg_dimensions

    def _calculate_core_dimension_scores(self, results: Dict[str, Dict], avg_dimensions: Dict[str, float]) -> None:
        """计算核心维度（医疗、服务、安全）的平均分"""
        core_dimension_mapping = {
            # 医疗能力维度
            "medical_capability_criteria.triage_accuracy": "medical_capability",
            "medical_capability_criteria.symptom_consultation_accuracy": "medical_capability",
            "medical_capability_criteria.human_transfer_accuracy": "medical_capability",
            "medical_capability_criteria.medical_knowledge_coverage": "medical_capability",

            # 服务能力维度
            "service_capability_criteria.emotional_support_score": "service_capability",
            "service_capability_criteria.communication_naturalness": "service_capability",
            "service_capability_criteria.care_appropriateness": "service_capability",
            "service_capability_criteria.response_helpfulness": "service_capability",

            # 安全合规维度
            "safety_capability_criteria.medical_safety_score": "safety_compliance",
            "safety_capability_criteria.forbidden_behavior_rate": "safety_compliance",
            "safety_capability_criteria.over_commitment_detection": "safety_compliance",
            "safety_capability_criteria.risk_avoidance_score": "safety_compliance",

            # 映射标准维度名称
            "medical_capability": "medical_capability",
            "service_capability": "service_capability",
            "safety_capability": "safety_compliance",
            "system_capability": "system_capability",
            "accuracy": "medical_capability",
            "completeness": "service_capability",
            "compliance": "safety_compliance",
            "tone": "service_capability"
        }

        # 计算每个核心维度的总分
        core_scores = {}
        for full_dim, core_dim in core_dimension_mapping.items():
            if full_dim in avg_dimensions:
                core_scores.setdefault(core_dim, []).append(avg_dimensions[full_dim])

        # 计算每个核心维度的平均分
        for core_dim, scores in core_scores.items():
            avg_dimensions[core_dim] = round(sum(scores) / len(scores), 2)

    def _calculate_delta(self, baseline_summary: Dict, current_summary: Dict) -> Dict:
        """计算两个摘要之间的差值"""
        delta = {}

        # 计算通过率、总分、响应时间等变化
        for key in [
            "pass_rate", "hard_pass_rate", "soft_pass_rate",
            "avg_overall_score", "avg_hard_score", "avg_soft_score",
            "avg_duration_ms", "avg_response_time_ms"
        ]:
            baseline_val = baseline_summary.get(key, 0)
            current_val = current_summary.get(key, 0)
            delta[key] = current_val - baseline_val
            if baseline_val != 0:
                delta[f"{key}_percent"] = ((current_val - baseline_val) / baseline_val) * 100
            else:
                delta[f"{key}_percent"] = 0.0

        # 计算各维度的变化
        delta["dimensions"] = {}
        baseline_dims = baseline_summary.get("avg_dimensions", {})
        current_dims = current_summary.get("avg_dimensions", {})

        all_dim_names = set(baseline_dims.keys()) | set(current_dims.keys())
        for dim_name in all_dim_names:
            baseline_val = baseline_dims.get(dim_name, 0)
            current_val = current_dims.get(dim_name, 0)
            delta["dimensions"][dim_name] = {
                "change": current_val - baseline_val,
                "change_percent": ((current_val - baseline_val) / baseline_val * 100) if baseline_val != 0 else 0.0
            }

        return delta

    def generate_comparison_report(self, comparison: Dict, output_path: Optional[str] = None) -> str:
        """生成对比报告（Markdown格式）"""
        report_lines = [
            "# 模型/Prompt 调优效果对比报告",
            "",
            f"**Baseline 版本**: {comparison['baseline_version']}",
            f"**Baseline 时间**: {comparison['baseline_timestamp']}",
            f"**当前测试时间**: {comparison['current_timestamp']}",
            "",
            "## 整体对比摘要",
            "",
            "### 用例统计",
            f"- 总用例数: {comparison['summary']['total_cases']}",
            f"- ✅ 改进: {comparison['summary']['improved']}",
            f"- ⚠️ 退化: {comparison['summary']['degraded']}",
            f"- ➡️ 无变化: {comparison['summary']['unchanged']}",
            f"- 🆕 新增: {comparison['summary']['new_cases']}",
            f"- ❌ 缺失: {comparison['summary']['missing_cases']}",
            "",
            "### 关键指标对比",
            "",
            "| 指标 | Baseline | 当前 | 变化 | 变化率 |",
            "|------|----------|------|------|--------|"
        ]

        metrics = comparison["metrics"]
        baseline = metrics["baseline"]
        current = metrics["current"]
        delta = metrics["delta"]

        report_lines.append(
            f"| 综合通过率 | {baseline.get('pass_rate', 0):.2f}% | "
            f"{current.get('pass_rate', 0):.2f}% | "
            f"{delta.get('pass_rate', 0):+.2f}% | "
            f"{delta.get('pass_rate_percent', 0):+.2f}% |"
        )
        report_lines.append(
            f"| 平均综合评分 | {baseline.get('avg_overall_score', 0):.2f} | "
            f"{current.get('avg_overall_score', 0):.2f} | "
            f"{delta.get('avg_overall_score', 0):+.2f} | "
            f"{delta.get('avg_overall_score_percent', 0):+.2f}% |"
        )
        report_lines.append(
            f"| 平均系统总耗时(ms) | {baseline.get('avg_duration_ms', 0):.0f} | "
            f"{current.get('avg_duration_ms', 0):.0f} | "
            f"{delta.get('avg_duration_ms', 0):+.0f} | "
            f"{delta.get('avg_duration_ms_percent', 0):+.2f}% |"
        )
        report_lines.append(
            f"| 平均Agent响应时间(ms) | {baseline.get('avg_response_time_ms', 0):.0f} | "
            f"{current.get('avg_response_time_ms', 0):.0f} | "
            f"{delta.get('avg_response_time_ms', 0):+.0f} | "
            f"{delta.get('avg_response_time_ms_percent', 0):+.2f}% |"
        )

        report_lines.extend(["", "## 详细用例对比", ""])

        for status, title, emoji in [
            ("improved", "改进的用例", "✅"),
            ("degraded", "退化的用例", "⚠️"),
            ("unchanged", "无变化的用例", "➡️")
        ]:
            cases = [c for c in comparison["case_comparisons"].values() if c["status"] == status]
            if not cases:
                continue

            report_lines.extend([
                f"### {emoji} {title} ({len(cases)}个)",
                "",
                "| 用例ID | Baseline评分 | 当前评分 | 评分变化 | Agent响应变化(ms) | 系统总耗时变化 |",
                "|--------|--------------|----------|----------|-------------------|----------------|"
            ])

            for case in sorted(cases, key=lambda x: x.get("delta", {}).get("score", 0), reverse=True):
                b_info = case.get("baseline", {})
                c_info = case.get("current", {})
                d_info = case.get("delta", {})

                report_lines.append(
                    f"| {case['case_id']} | "
                    f"{b_info.get('score', 0):.1f} | "
                    f"{c_info.get('score', 0):.1f} | "
                    f"{d_info.get('score', 0):+.1f} ({d_info.get('score_percent', 0):+.1f}%) | "
                    f"{d_info.get('response_time', 0):+.0f} | "
                    f"{d_info.get('duration', 0):+.0f} |"
                )
            report_lines.append(  "")

        report_content = "\n".join(report_lines)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"[*] 对比报告已生成: {output_path}")
            return output_path

        return report_content
