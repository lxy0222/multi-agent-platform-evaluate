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
        
        baseline_data = {
            "version": version_name,
            "timestamp": timestamp,
            "metadata": metadata or {},
            "results": results,
            "summary": self._calculate_summary(results)
        }
        
        # 保存两份：一份带时间戳（历史记录），一份最新版本
        timestamped_file = self.baseline_dir / f"{version_name}_{timestamp}.json"
        latest_file = self.baseline_dir / f"{version_name}_latest.json"
        
        for filepath in [timestamped_file, latest_file]:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(baseline_data, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] Baseline 已保存: {latest_file}")
        return str(latest_file)
    
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
                "improved": 0,
                "degraded": 0,
                "unchanged": 0,
                "new_cases": 0,
                "missing_cases": 0
            },
            "metrics": {
                "baseline": baseline.get("summary", {}),
                "current": self._calculate_summary(current_results),
                "delta": {}
            }
        }
        
        # 逐个用例对比
        all_case_ids = set(baseline_results.keys()) | set(current_results.keys())
        comparison["summary"]["total_cases"] = len(all_case_ids)
        
        for case_id in all_case_ids:
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
        """对比单个测试用例"""
        if not baseline_case and current_case:
            return {
                "status": "new",
                "case_id": case_id,
                "baseline": None,
                "current": current_case,
                "delta": {}
            }
        
        if baseline_case and not current_case:
            return {
                "status": "missing",
                "case_id": case_id,
                "baseline": baseline_case,
                "current": None,
                "delta": {}
            }
        
        baseline_score = baseline_case.get("llm_score", 0) if baseline_case else 0
        current_score = current_case.get("llm_score", 0) if current_case else 0
        baseline_passed = baseline_case.get("validation_passed", False) if baseline_case else False
        current_passed = current_case.get("validation_passed", False) if current_case else False
        baseline_duration = baseline_case.get("duration_ms", 0) if baseline_case else 0
        current_duration = current_case.get("duration_ms", 0) if current_case else 0
        baseline_response_time = baseline_case.get("response_time_ms", 0) if baseline_case else 0
        current_response_time = current_case.get("response_time_ms", 0) if current_case else 0
        
        delta = {
            "score": current_score - baseline_score,
            "score_percent": ((current_score - baseline_score) / max(baseline_score, 1)) * 100,
            "duration": current_duration - baseline_duration,
            "duration_percent": ((current_duration - baseline_duration) / max(baseline_duration, 1)) * 100,
            "response_time": current_response_time - baseline_response_time,
            "response_time_percent": ((current_response_time - baseline_response_time) / max(baseline_response_time, 1)) * 100,
            "validation_changed": baseline_passed != current_passed
        }
        
        if not baseline_passed and current_passed:
            status = "improved"
        elif baseline_passed and not current_passed:
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
            "baseline": {
                "score": baseline_score,
                "passed": baseline_passed,
                "duration_ms": baseline_duration,
                "response_time_ms": baseline_response_time,
                "reason": baseline_case.get("llm_reason", "") if baseline_case else ""
            },
            "current": {
                "score": current_score,
                "passed": current_passed,
                "duration_ms": current_duration,
                "response_time_ms": current_response_time,
                "reason": current_case.get("llm_reason", "") if current_case else ""
            },
            "delta": delta
        }
    
    def _calculate_summary(self, results: Dict[str, Dict]) -> Dict:
        """计算测试结果的统计摘要"""
        if not results:
            return {
                "total_cases": 0,
                "passed_cases": 0,
                "failed_cases": 0,
                "pass_rate": 0.0,
                "avg_overall_score": 0.0,
                "avg_duration_ms": 0.0,
                "avg_response_time_ms": 0.0,
                "avg_dimensions": {}
            }
        
        total = len(results)
        passed = sum(1 for r in results.values() if r.get("validation_passed", False))
        scores = [r.get("overall_score", 0) for r in results.values() if "overall_score" in r]
        durations = [r.get("duration_ms", 0) for r in results.values() if "duration_ms" in r]
        response_times = [r.get("response_time_ms", 0) for r in results.values() if "response_time_ms" in r]
        
        # 计算各维度的平均分
        avg_dimensions = {}
        
        # 收集所有维度和子维度
        all_dimensions = {}
        for r in results.values():
            dims = r.get("dimensions", {})
            if isinstance(dims, dict):
                for dim_key, dim_value in dims.items():
                    if isinstance(dim_value, dict):
                        # 处理嵌套维度结构（如 medical_capability_criteria）
                        for sub_key, sub_value in dim_value.items():
                            if isinstance(sub_value, dict) and "score" in sub_value:
                                full_key = f"{dim_key}.{sub_key}"
                                all_dimensions.setdefault(full_key, []).append(sub_value["score"])
                            elif isinstance(sub_value, (int, float)):
                                full_key = f"{dim_key}.{sub_key}"
                                all_dimensions.setdefault(full_key, []).append(sub_value)
                    elif isinstance(dim_value, dict) and "score" in dim_value:
                        # 处理扁平维度结构
                        all_dimensions.setdefault(dim_key, []).append(dim_value["score"])
                    elif isinstance(dim_value, (int, float)):
                        # 直接数值
                        all_dimensions.setdefault(dim_key, []).append(dim_value)
        
        # 计算每个维度的平均分
        for dim_name, scores_list in all_dimensions.items():
            if scores_list:
                avg_dimensions[dim_name] = round(sum(scores_list) / len(scores_list), 2)
        
        # 同时计算核心维度的平均分（从嵌套结构中提取）
        self._calculate_core_dimension_scores(results, avg_dimensions)
        
        avg_overall_score = sum(scores) / len(scores) if scores else 0.0
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
        
        return {
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": total - passed,
            "pass_rate": (passed / total * 100) if total > 0 else 0.0,
            "avg_overall_score": avg_overall_score,
            "avg_duration_ms": avg_duration,
            "avg_response_time_ms": avg_response_time,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "avg_dimensions": avg_dimensions  # 新增：各维度平均分
        }
    
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
        for key in ["pass_rate", "avg_overall_score", "avg_duration_ms", "avg_response_time_ms"]:
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
            f"| 通过率 | {baseline.get('pass_rate', 0):.2f}% | "
            f"{current.get('pass_rate', 0):.2f}% | "
            f"{delta.get('pass_rate', 0):+.2f}% | "
            f"{delta.get('pass_rate_percent', 0):+.2f}% |"
        )
        report_lines.append(
            f"| 平均评分 | {baseline.get('avg_score', 0):.2f} | "
            f"{current.get('avg_score', 0):.2f} | "
            f"{delta.get('avg_score', 0):+.2f} | "
            f"{delta.get('avg_score_percent', 0):+.2f}% |"
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
