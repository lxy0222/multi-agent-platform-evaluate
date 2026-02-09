"""
对比报告生成器
用于生成详细的模型/Prompt调优对比报告
支持多维度评估和可视化
"""
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime


class ComparisonReporter:
    """对比报告生成器"""
    
    def __init__(self, comparison_data: Dict, metrics_config: Optional[Dict] = None):
        """
        初始化报告生成器
        
        Args:
            comparison_data: 对比数据
            metrics_config: 评估维度配置
        """
        self.data = comparison_data
        self.metrics_config = metrics_config or {}
    
    def generate_markdown_report(self, output_path: Optional[str] = None) -> str:
        """
        生成Markdown格式的对比报告
        
        Args:
            output_path: 输出文件路径
        
        Returns:
            报告内容
        """
        sections = [
            self._generate_header(),
            self._generate_executive_summary(),
            self._generate_metrics_comparison(),
            self._generate_dimension_analysis(),
            self._generate_case_details(),
            self._generate_recommendations(),
            self._generate_footer()
        ]
        
        report_content = "\n\n".join(sections)
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"[*] Markdown报告已生成: {output_path}")
        
        return report_content
    
    def _generate_header(self) -> str:
        """生成报告头部"""
        return f"""# 🔬 模型/Prompt 调优效果对比报告

**报告生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## 📋 基本信息

| 项目 | Baseline版本 | 当前版本 |
|------|-------------|---------|
| **版本名称** | {self.data.get('baseline_version', 'N/A')} | Current Run |
| **测试时间** | {self.data.get('baseline_timestamp', 'N/A')} | {self.data.get('current_timestamp', 'N/A')} |
| **模型配置** | {self.data.get('baseline_metadata', {}).get('model', 'N/A')} | {self.data.get('current_metadata', {}).get('model', 'N/A')} |
| **测试用例数** | {self.data.get('metrics', {}).get('baseline', {}).get('total_cases', 0)} | {self.data.get('metrics', {}).get('current', {}).get('total_cases', 0)} |

---"""
    
    def _generate_executive_summary(self) -> str:
        """生成执行摘要"""
        summary = self.data.get('summary', {})
        metrics = self.data.get('metrics', {})
        delta = metrics.get('delta', {})
        
        # 判断整体趋势
        score_change = delta.get('avg_score', 0)
        pass_rate_change = delta.get('pass_rate', 0)
        
        if score_change > 5 or pass_rate_change > 3:
            trend_emoji = "📈"
            trend_text = "**整体改进**"
            trend_color = "🟢"
        elif score_change < -5 or pass_rate_change < -3:
            trend_emoji = "📉"
            trend_text = "**整体退化**"
            trend_color = "🔴"
        else:
            trend_emoji = "➡️"
            trend_text = "**基本持平**"
            trend_color = "🟡"
        
        return f"""## {trend_emoji} 执行摘要

{trend_color} **评估结论**: {trend_text}

### 用例变化统计

| 指标 | 数量 | 占比 |
|------|------|------|
| ✅ **改进用例** | {summary.get('improved', 0)} | {summary.get('improved', 0) / max(summary.get('total_cases', 1), 1) * 100:.1f}% |
| ⚠️ **退化用例** | {summary.get('degraded', 0)} | {summary.get('degraded', 0) / max(summary.get('total_cases', 1), 1) * 100:.1f}% |
| ➡️ **无变化用例** | {summary.get('unchanged', 0)} | {summary.get('unchanged', 0) / max(summary.get('total_cases', 1), 1) * 100:.1f}% |
| 🆕 **新增用例** | {summary.get('new_cases', 0)} | - |
| ❌ **缺失用例** | {summary.get('missing_cases', 0)} | - |
| **总计** | {summary.get('total_cases', 0)} | 100% |

### 关键发现

{self._generate_key_findings(score_change, pass_rate_change, delta)}

---"""
    
    def _generate_key_findings(self, score_change: float, pass_rate_change: float, delta: Dict) -> str:
        """生成关键发现"""
        findings = []
        
        if abs(score_change) >= 10:
            direction = "提升" if score_change > 0 else "下降"
            findings.append(f"- 🎯 **平均评分{direction}显著**: {score_change:+.2f}分 (变化率: {delta.get('avg_score_percent', 0):+.1f}%)")
        
        if abs(pass_rate_change) >= 5:
            direction = "提升" if pass_rate_change > 0 else "下降"
            findings.append(f"- 📊 **通过率{direction}明显**: {pass_rate_change:+.2f}% (变化率: {delta.get('pass_rate_percent', 0):+.1f}%)")
        
        duration_change = delta.get('avg_duration_ms', 0)
        if abs(duration_change) >= 500:
            direction = "加快" if duration_change < 0 else "变慢"
            findings.append(f"- ⚡ **响应速度{direction}**: {duration_change:+.0f}ms (变化率: {delta.get('avg_duration_ms_percent', 0):+.1f}%)")
        
        if not findings:
            findings.append("- ℹ️ 各项指标变化在正常范围内，无显著变化")
        
        return "\n".join(findings)
    
    def _generate_metrics_comparison(self) -> str:
        """生成指标对比表"""
        metrics = self.data.get('metrics', {})
        baseline = metrics.get('baseline', {})
        current = metrics.get('current', {})
        delta = metrics.get('delta', {})
        
        return f"""## 📊 核心指标对比

### 准确性指标

| 指标 | Baseline | 当前版本 | 变化量 | 变化率 | 趋势 |
|------|----------|----------|--------|--------|------|
| **通过率** | {baseline.get('pass_rate', 0):.2f}% | {current.get('pass_rate', 0):.2f}% | {delta.get('pass_rate', 0):+.2f}% | {delta.get('pass_rate_percent', 0):+.2f}% | {self._get_trend_arrow(delta.get('pass_rate', 0))} |
| **平均评分** | {baseline.get('avg_score', 0):.2f} | {current.get('avg_score', 0):.2f} | {delta.get('avg_score', 0):+.2f} | {delta.get('avg_score_percent', 0):+.2f}% | {self._get_trend_arrow(delta.get('avg_score', 0))} |
| **最高分** | {baseline.get('max_score', 0):.2f} | {current.get('max_score', 0):.2f} | {current.get('max_score', 0) - baseline.get('max_score', 0):+.2f} | - | {self._get_trend_arrow(current.get('max_score', 0) - baseline.get('max_score', 0))} |
| **最低分** | {baseline.get('min_score', 0):.2f} | {current.get('min_score', 0):.2f} | {current.get('min_score', 0) - baseline.get('min_score', 0):+.2f} | - | {self._get_trend_arrow(current.get('min_score', 0) - baseline.get('min_score', 0))} |

### 性能指标

| 指标 | Baseline | 当前版本 | 变化量 | 变化率 | 趋势 |
|------|----------|----------|--------|--------|------|
| **平均响应时间** | {baseline.get('avg_duration_ms', 0):.0f}ms | {current.get('avg_duration_ms', 0):.0f}ms | {delta.get('avg_duration_ms', 0):+.0f}ms | {delta.get('avg_duration_ms_percent', 0):+.2f}% | {self._get_trend_arrow(-delta.get('avg_duration_ms', 0))} |

> 💡 **说明**: 
> - ⬆️ 表示改进 | ⬇️ 表示退化 | ➡️ 表示持平
> - 响应时间的趋势箭头相反（越短越好）

---"""
    
    def _get_trend_arrow(self, value: float, threshold: float = 2.0) -> str:
        """获取趋势箭头"""
        if value > threshold:
            return "⬆️ 改进"
        elif value < -threshold:
            return "⬇️ 退化"
        else:
            return "➡️ 持平"
    
    def _generate_dimension_analysis(self) -> str:
        """生成维度分析"""
        metrics = self.data.get('metrics', {})
        baseline = metrics.get('baseline', {})
        current = metrics.get('current', {})
        delta = metrics.get('delta', {})
        
        baseline_dims = baseline.get('avg_dimensions', {})
        current_dims = current.get('avg_dimensions', {})
        delta_dims = delta.get('dimensions', {})
        
        if not baseline_dims and not current_dims:
            return ""
        
        lines = [
            "## 🎯 多维度详细分析",
            "",
            "### 各维度评分对比",
            "",
            "| 维度 | Baseline | 当前版本 | 变化量 | 变化率 | 趋势 |",
            "|------|----------|----------|--------|--------|------|"
        ]
        
        # 合并所有维度名称
        all_dims = set(baseline_dims.keys()) | set(current_dims.keys())
        
        # 维度名称映射
        dim_names_map = {
            "accuracy": "准确性",
            "completeness": "完整性",
            "compliance": "合规性",
            "tone": "语气亲和度"
        }
        
        for dim_key in sorted(all_dims):
            dim_display_name = dim_names_map.get(dim_key, dim_key.capitalize())
            baseline_score = baseline_dims.get(dim_key, 0)
            current_score = current_dims.get(dim_key, 0)
            
            if dim_key in delta_dims:
                change = delta_dims[dim_key].get("change", 0)
                change_percent = delta_dims[dim_key].get("change_percent", 0)
            else:
                change = current_score - baseline_score
                change_percent = ((current_score - baseline_score) / baseline_score * 100) if baseline_score != 0 else 0
            
            trend = self._get_trend_arrow(change, threshold=2.0)
            
            lines.append(
                f"| {dim_display_name} | "
                f"{baseline_score:.1f} | "
                f"{current_score:.1f} | "
                f"{change:+.1f} | "
                f"{change_percent:+.1f}% | "
                f"{trend} |"
            )
        
        lines.extend([
            "",
            "### 维度分析说明",
            "",
            self._analyze_dimension_changes(baseline_dims, current_dims, delta_dims),
            "",
            "---"
        ])
        
        return "\n".join(lines)
    
    def _analyze_dimension_changes(
        self,
        baseline_dims: Dict,
        current_dims: Dict,
        delta_dims: Dict
    ) -> str:
        """分析维度变化并生成说明"""
        findings = []
        
        dim_names_map = {
            "accuracy": "准确性",
            "completeness": "完整性",
            "compliance": "合规性",
            "tone": "语气亲和度"
        }
        
        for dim_key in delta_dims:
            change = delta_dims[dim_key].get("change", 0)
            change_percent = delta_dims[dim_key].get("change_percent", 0)
            dim_name = dim_names_map.get(dim_key, dim_key)
            
            if abs(change) >= 5:  # 变化超过5分才记录
                direction = "提升" if change > 0 else "下降"
                trend_icon = "+" if change > 0 else "-"
                findings.append(
                    f"- [{trend_icon}] **{dim_name}{direction}**: "
                    f"{change:+.1f}分 ({change_percent:+.1f}%)"
                )
        
        if not findings:
            findings.append("- 各维度评分变化在正常范围内，无显著变化")
        
        return "\n".join(findings)
    
    def _generate_case_details(self) -> str:
        """生成用例详情"""
        case_comparisons = self.data.get('case_comparisons', {})
        
        sections = []
        
        # 改进的用例
        improved_cases = [c for c in case_comparisons.values() if c.get('status') == 'improved']
        if improved_cases:
            sections.append(self._format_case_section(
                "✅ 改进的用例",
                improved_cases,
                sort_key=lambda x: x.get('delta', {}).get('score', 0),
                reverse=True
            ))
        
        # 退化的用例
        degraded_cases = [c for c in case_comparisons.values() if c.get('status') == 'degraded']
        if degraded_cases:
            sections.append(self._format_case_section(
                "⚠️ 退化的用例",
                degraded_cases,
                sort_key=lambda x: x.get('delta', {}).get('score', 0),
                reverse=False
            ))
        
        # 无变化的用例(可选,通常不展示)
        # unchanged_cases = [c for c in case_comparisons.values() if c.get('status') == 'unchanged']
        
        if not sections:
            return "## 📝 用例详情\n\n> 暂无显著变化的用例"
        
        return "## 📝 用例详情\n\n" + "\n\n".join(sections) + "\n\n---"
    
    def _format_case_section(
        self,
        title: str,
        cases: List[Dict],
        sort_key=None,
        reverse: bool = True
    ) -> str:
        """格式化用例段落"""
        if not cases:
            return ""
        
        if sort_key:
            cases = sorted(cases, key=sort_key, reverse=reverse)
        
        lines = [f"### {title} ({len(cases)}个)\n"]
        lines.append("| 用例ID | Baseline评分 | 当前评分 | 评分变化 | 通过状态 | 响应时间变化 |")
        lines.append("|--------|--------------|----------|----------|----------|--------------|")
        
        for case in cases:
            baseline_info = case.get('baseline', {})
            current_info = case.get('current', {})
            delta_info = case.get('delta', {})
            
            case_id = case.get('case_id', 'N/A')
            baseline_score = baseline_info.get('score', 0)
            current_score = current_info.get('score', 0)
            score_delta = delta_info.get('score', 0)
            
            baseline_pass = "✅" if baseline_info.get('passed') else "❌"
            current_pass = "✅" if current_info.get('passed') else "❌"
            pass_status = f"{baseline_pass} → {current_pass}"
            
            duration_delta = delta_info.get('duration', 0)
            
            lines.append(
                f"| {case_id} | "
                f"{baseline_score:.1f} | "
                f"{current_score:.1f} | "
                f"{score_delta:+.1f} ({delta_info.get('score_percent', 0):+.1f}%) | "
                f"{pass_status} | "
                f"{duration_delta:+.0f}ms |"
            )
        
        # 添加详细原因(可选,前3个)
        if len(cases) > 0:
            lines.append("\n**详细分析**:\n")
            for i, case in enumerate(cases[:3], 1):
                case_id = case.get('case_id', 'N/A')
                current_reason = case.get('current', {}).get('reason', '')
                if current_reason:
                    lines.append(f"{i}. **{case_id}**: {current_reason}")
        
        return "\n".join(lines)
    
    def _generate_recommendations(self) -> str:
        """生成改进建议"""
        summary = self.data.get('summary', {})
        metrics = self.data.get('metrics', {})
        delta = metrics.get('delta', {})
        
        recommendations = []
        
        # 基于退化用例的建议
        if summary.get('degraded', 0) > 0:
            degraded_ratio = summary.get('degraded', 0) / max(summary.get('total_cases', 1), 1)
            if degraded_ratio > 0.2:  # 超过20%退化
                recommendations.append(
                    "⚠️ **高优先级**: 超过20%的用例出现退化，建议仔细review prompt变更，考虑回滚"
                )
            else:
                recommendations.append(
                    "⚡ 少量用例退化，建议针对性优化这些用例的prompt"
                )
        
        # 基于性能变化的建议
        duration_change_percent = delta.get('avg_duration_ms_percent', 0)
        if duration_change_percent > 20:
            recommendations.append(
                "🐌 响应时间显著增加，建议检查模型配置和网络延迟"
            )
        elif duration_change_percent < -20:
            recommendations.append(
                "⚡ 响应速度显著提升，这是一个积极的改进"
            )
        
        # 基于评分变化的建议
        score_change = delta.get('avg_score', 0)
        if score_change > 10:
            recommendations.append(
                "🎉 评分显著提升，建议保存此版本为新的baseline"
            )
        
        if not recommendations:
            recommendations.append(
                "✅ 各项指标稳定，可继续进行其他优化尝试"
            )
        
        return f"""## 💡 改进建议

{chr(10).join(f'{i}. {rec}' for i, rec in enumerate(recommendations, 1))}

---"""
    
    def _generate_footer(self) -> str:
        """生成报告尾部"""
        return f"""## 📌 附录

### 如何使用本报告

1. **关注改进和退化用例**: 重点查看评分变化超过±10分的用例
2. **对比Baseline**: 确保新版本在关键业务场景上不低于baseline
3. **性能权衡**: 在准确性和响应时间之间找到平衡点
4. **持续优化**: 基于本报告的发现，迭代优化prompt和模型配置

### 下一步行动

- [ ] Review退化用例的详细日志
- [ ] 针对退化场景优化prompt
- [ ] 如果整体改进明显，更新baseline
- [ ] 记录本次调优的经验教训

---

**报告生成器**: ComparisonReporter v1.0  
**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"""
    
    def generate_json_report(self, output_path: Optional[str] = None) -> str:
        """
        生成JSON格式的对比报告
        
        Args:
            output_path: 输出文件路径
        
        Returns:
            JSON字符串
        """
        json_data = {
            "report_meta": {
                "generated_at": datetime.now().isoformat(),
                "report_version": "1.0"
            },
            "comparison_data": self.data
        }
        
        json_str = json.dumps(json_data, ensure_ascii=False, indent=2)
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            print(f"[*] JSON报告已生成: {output_path}")
        
        return json_str
