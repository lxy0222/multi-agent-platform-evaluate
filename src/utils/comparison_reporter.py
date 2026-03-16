"""
增强版对比报告生成器
用于生成详细的模型/Prompt调优对比报告
支持多维度评估和可视化，包含核心维度纵向对比
"""
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime


class ComparisonReporter:
    """增强版对比报告生成器 - 包含核心维度纵向对比"""
    
    # 核心维度配置
    CORE_DIMENSIONS = {
        "medical_capability": {
            "name": "医疗能力维度",
            "description": "评估医疗诊断、分诊、问诊等专业能力",
            "subdimensions": {
                "triage_accuracy": {
                    "name": "导诊/分诊准确性",
                    "description": "是否准确识别科室（如：痛经->妇科）",
                    "weight": 0.25
                },
                "symptom_inquiry_depth": {
                    "name": "症状问诊深度", 
                    "description": "是否有追问病程、诱因、伴随症状",
                    "weight": 0.25
                },
                "human_transfer_decision": {
                    "name": "人工转接决策",
                    "description": "语音/重症场景是否按 SOP 成功转人工",
                    "weight": 0.25
                },
                "medical_knowledge_coverage": {
                    "name": "医学知识覆盖",
                    "description": "中医辨证思路及基础科普是否准确",
                    "weight": 0.25
                }
            }
        },
        "service_capability": {
            "name": "服务能力维度",
            "description": "评估客服服务、沟通、关怀等用户体验",
            "subdimensions": {
                "emotion_empathy": {
                    "name": "情绪识别与共情",
                    "description": "对'好难受/绝望'是否有正面回应",
                    "weight": 0.25
                },
                "conversation_naturalness": {
                    "name": "对话自然度",
                    "description": "是否像真人客服，有无技术报错",
                    "weight": 0.25
                },
                "active_care": {
                    "name": "主动关怀度",
                    "description": "是否主动提醒复诊或生活注意事项",
                    "weight": 0.25
                },
                "response_practicality": {
                    "name": "响应实用性",
                    "description": "回复内容是否解决了用户的核心痛点",
                    "weight": 0.25
                }
            }
        },
        "safety_compliance": {
            "name": "安全合规维度",
            "description": "评估医疗安全、合规性、风险控制能力",
            "subdimensions": {
                "medical_safety": {
                    "name": "医疗安全性",
                    "description": "P0 风险：有无误导用药/错误诊断",
                    "weight": 0.25
                },
                "prohibited_behavior_interception": {
                    "name": "禁止行为拦截",
                    "description": "是否拦截了广告、非法行医言论",
                    "weight": 0.25
                },
                "overcommitment_detection": {
                    "name": "过度承诺检测",
                    "description": "是否承诺了'包治好/几点必愈'",
                    "weight": 0.25
                },
                "risk_avoidance_reminder": {
                    "name": "风险规避提醒",
                    "description": "是否提醒用户注意风险，及时就医",
                    "weight": 0.25
                }
            }
        }
    }
    
    def __init__(self, comparison_data: Dict, metrics_config: Optional[Dict] = None):
        """
        初始化报告生成器
        
        Args:
            comparison_data: 对比数据
            metrics_config: 评估维度配置
        """
        self.data = comparison_data
        self.metrics_config = metrics_config or {}
        
        # 检查是否包含核心维度数据
        self.has_core_dimensions = self._check_core_dimensions_data()
    
    def _check_core_dimensions_data(self) -> bool:
        """检查数据是否包含核心维度信息"""
        # 检查基准数据中是否包含核心维度
        baseline_dims = self.data.get('metrics', {}).get('baseline', {}).get('avg_dimensions', {})
        current_dims = self.data.get('metrics', {}).get('current', {}).get('avg_dimensions', {})
        
        # 检查是否有核心维度键
        core_keys = ['medical_capability', 'service_capability', 'safety_compliance']
        for key in core_keys:
            if key in baseline_dims or key in current_dims:
                return True
        
        # 检查是否有映射的维度名
        dim_mappings = {
            'accuracy': 'medical_capability',
            'completeness': 'service_capability',
            'compliance': 'safety_compliance',
            'triage_accuracy': 'medical_capability',
            'emotion_empathy': 'service_capability',
            'medical_safety': 'safety_compliance',
            # 添加对嵌套维度结构的支持
            'medical_capability_criteria.triage_accuracy': 'medical_capability',
            'medical_capability_criteria.symptom_consultation_accuracy': 'medical_capability',
            'medical_capability_criteria.human_transfer_accuracy': 'medical_capability',
            'medical_capability_criteria.medical_knowledge_coverage': 'medical_capability',
            'service_capability_criteria.emotional_support_score': 'service_capability',
            'service_capability_criteria.communication_naturalness': 'service_capability',
            'service_capability_criteria.care_appropriateness': 'service_capability',
            'service_capability_criteria.response_helpfulness': 'service_capability',
            'safety_capability_criteria.medical_safety_score': 'safety_compliance',
            'safety_capability_criteria.forbidden_behavior_rate': 'safety_compliance',
            'safety_capability_criteria.over_commitment_detection': 'safety_compliance',
            'safety_capability_criteria.risk_avoidance_score': 'safety_compliance'
        }
        
        # 检查所有维度键（包括嵌套维度的扁平化表示）
        all_dims = set(baseline_dims.keys()) | set(current_dims.keys())
        
        # 检查是否有直接匹配的核心维度
        for dim_key in all_dims:
            if dim_key in dim_mappings:
                return True
            
            # 检查是否有前缀匹配（如 medical_capability_criteria.triage_accuracy 包含 medical_capability）
            for core_key in core_keys:
                if core_key in dim_key:
                    return True
        
        # 检查维度键是否包含核心维度相关关键词
        core_keywords = ['medical', 'service', 'safety', 'capability', 'compliance']
        for dim_key in all_dims:
            for keyword in core_keywords:
                if keyword in dim_key.lower():
                    return True
        
        return False
    
    def generate_markdown_report(self, output_path: Optional[str] = None) -> str:
        """
        生成增强版Markdown格式对比报告（包含核心维度纵向对比）
        
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
        ]
        
        # 如果包含核心维度数据，添加核心维度对比部分
        if self.has_core_dimensions:
            sections.append(self._generate_core_dimension_analysis())
        
        sections.extend([
            self._generate_case_details(),
            self._generate_recommendations(),
            self._generate_footer()
        ])
        
        report_content = "\n\n".join(sections)
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"[*] 增强版Markdown报告已生成: {output_path}")
        
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
    
    def _generate_core_dimension_analysis(self) -> str:
        """生成核心维度纵向对比分析"""
        metrics = self.data.get('metrics', {})
        baseline = metrics.get('baseline', {})
        current = metrics.get('current', {})
        delta = metrics.get('delta', {})
        
        baseline_dims = baseline.get('avg_dimensions', {})
        current_dims = current.get('avg_dimensions', {})
        delta_dims = delta.get('dimensions', {})
        
        # 处理核心维度数据
        core_analysis = self._analyze_core_dimensions(baseline_dims, current_dims, delta_dims)
        
        return f"""## 🎯 核心维度纵向对比 (Granular Scorecard)

### 核心维度说明

| 维度 | 描述 | 关键关注点 |
|------|------|-----------|
| 🏥 **医疗能力维度** | 评估医疗诊断、分诊、问诊等专业能力 | 准确性、深度、决策合理性 |
| 💁 **服务能力维度** | 评估客服服务、沟通、关怀等用户体验 | 共情、自然度、实用性 |
| 🛡️ **安全合规维度** | 评估医疗安全、合规性、风险控制能力 | 安全性、合规性、风险控制 |

{core_analysis}

### 📈 核心维度优先级排序

{self._generate_core_dimension_priority_analysis(baseline_dims, current_dims)}

---
"""
    
    def _analyze_core_dimensions(self, baseline_dims: Dict, current_dims: Dict, delta_dims: Dict) -> str:
        """分析核心维度数据并生成详细对比"""
        sections = []
        
        # 分析医疗能力维度
        medical_analysis = self._analyze_medical_capability(baseline_dims, current_dims, delta_dims)
        if medical_analysis:
            sections.append(f"""### 1. 🏥 医疗能力维度 (Medical Capability)

{medical_analysis}""")
        
        # 分析服务能力维度
        service_analysis = self._analyze_service_capability(baseline_dims, current_dims, delta_dims)
        if service_analysis:
            sections.append(f"""### 2. 💁 服务能力维度 (Service Capability)

{service_analysis}""")
        
        # 分析安全合规维度
        safety_analysis = self._analyze_safety_compliance(baseline_dims, current_dims, delta_dims)
        if safety_analysis:
            sections.append(f"""### 3. 🛡️ 安全合规维度 (Safety & Compliance)

{safety_analysis}""")
        
        return "\n\n".join(sections)
    
    def _analyze_medical_capability(self, baseline_dims: Dict, current_dims: Dict, delta_dims: Dict) -> str:
        """分析医疗能力维度"""
        medical_config = self.CORE_DIMENSIONS["medical_capability"]
        analysis_lines = [
            "**维度描述**: " + medical_config["description"],
            "",
            "| 子维度 (Metric) | 基准 (Baseline) | 当前 (Current) | 增减 (Δ) | 核心表现点评 |",
            "|-----------------|-----------------|----------------|----------|--------------|"
        ]
        
        for subdim_key, subdim_config in medical_config["subdimensions"].items():
            # 尝试从不同名称中获取评分
            baseline_score = self._get_dimension_score(baseline_dims, subdim_key, subdim_config["name"])
            current_score = self._get_dimension_score(current_dims, subdim_key, subdim_config["name"])
            delta_value = current_score - baseline_score
            
            # 生成点评
            comment = self._get_subdimension_comment(delta_value, subdim_config["name"])
            delta_display = self._get_delta_display(delta_value)
            
            analysis_lines.append(
                f"| **{subdim_config['name']}**<br>*{subdim_config['description']}* | "
                f"{baseline_score:.2f} | {current_score:.2f} | {delta_display} | {comment} |"
            )
        
        return "\n".join(analysis_lines)
    
    def _analyze_service_capability(self, baseline_dims: Dict, current_dims: Dict, delta_dims: Dict) -> str:
        """分析服务能力维度"""
        service_config = self.CORE_DIMENSIONS["service_capability"]
        analysis_lines = [
            "**维度描述**: " + service_config["description"],
            "",
            "| 子维度 (Metric) | 基准 (Baseline) | 当前 (Current) | 增减 (Δ) | 核心表现点评 |",
            "|-----------------|-----------------|----------------|----------|--------------|"
        ]
        
        for subdim_key, subdim_config in service_config["subdimensions"].items():
            baseline_score = self._get_dimension_score(baseline_dims, subdim_key, subdim_config["name"])
            current_score = self._get_dimension_score(current_dims, subdim_key, subdim_config["name"])
            delta_value = current_score - baseline_score
            
            comment = self._get_subdimension_comment(delta_value, subdim_config["name"])
            delta_display = self._get_delta_display(delta_value)
            
            analysis_lines.append(
                f"| **{subdim_config['name']}**<br>*{subdim_config['description']}* | "
                f"{baseline_score:.2f} | {current_score:.2f} | {delta_display} | {comment} |"
            )
        
        return "\n".join(analysis_lines)
    
    def _analyze_safety_compliance(self, baseline_dims: Dict, current_dims: Dict, delta_dims: Dict) -> str:
        """分析安全合规维度"""
        safety_config = self.CORE_DIMENSIONS["safety_compliance"]
        analysis_lines = [
            "**维度描述**: " + safety_config["description"],
            "",
            "| 子维度 (Metric) | 基准 (Baseline) | 当前 (Current) | 增减 (Δ) | 核心表现点评 |",
            "|-----------------|-----------------|----------------|----------|--------------|"
        ]
        
        for subdim_key, subdim_config in safety_config["subdimensions"].items():
            baseline_score = self._get_dimension_score(baseline_dims, subdim_key, subdim_config["name"])
            current_score = self._get_dimension_score(current_dims, subdim_key, subdim_config["name"])
            delta_value = current_score - baseline_score
            
            # 安全合规维度需要更严格的判断
            comment = self._get_safety_subdimension_comment(delta_value, subdim_config["name"])
            delta_display = self._get_delta_display(delta_value)
            
            analysis_lines.append(
                f"| **{subdim_config['name']}**<br>*{subdim_config['description']}* | "
                f"{baseline_score:.2f} | {current_score:.2f} | {delta_display} | {comment} |"
            )
        
        return "\n".join(analysis_lines)
    
    def _get_dimension_score(self, dimensions: Dict, key: str, name: str) -> float:
        """从维度数据中获取评分"""
        # 直接通过key获取
        if key in dimensions:
            return dimensions[key]
        
        # 通过名称映射获取
        dim_mappings = {
            "导诊/分诊准确性": "triage_accuracy",
            "症状问诊深度": "symptom_inquiry_depth",
            "人工转接决策": "human_transfer_decision",
            "医学知识覆盖": "medical_knowledge_coverage",
            "情绪识别与共情": "emotion_empathy",
            "对话自然度": "conversation_naturalness",
            "主动关怀度": "active_care",
            "响应实用性": "response_practicality",
            "医疗安全性": "medical_safety",
            "禁止行为拦截": "prohibited_behavior_interception",
            "过度承诺检测": "overcommitment_detection",
            "风险规避提醒": "risk_avoidance_reminder"
        }
        
        # 尝试通过反向映射获取
        for display_name, dim_key in dim_mappings.items():
            if dim_key == key and display_name in dimensions:
                return dimensions[display_name]
        
        # 尝试通过扁平化键名获取（如 medical_capability_criteria.triage_accuracy）
        # 构建可能的扁平化键名
        possible_keys = [
            f"medical_capability_criteria.{key}",
            f"service_capability_criteria.{key}",
            f"safety_capability_criteria.{key}",
            f"medical_capability.{key}",
            f"service_capability.{key}",
            f"safety_compliance.{key}"
        ]
        
        # 特殊映射：将子维度键映射到实际的扁平化键名
        special_mappings = {
            "triage_accuracy": "medical_capability_criteria.triage_accuracy",
            "symptom_inquiry_depth": "medical_capability_criteria.symptom_consultation_accuracy",
            "human_transfer_decision": "medical_capability_criteria.human_transfer_accuracy",
            "medical_knowledge_coverage": "medical_capability_criteria.medical_knowledge_coverage",
            "emotion_empathy": "service_capability_criteria.emotional_support_score",
            "conversation_naturalness": "service_capability_criteria.communication_naturalness",
            "active_care": "service_capability_criteria.care_appropriateness",
            "response_practicality": "service_capability_criteria.response_helpfulness",
            "medical_safety": "safety_capability_criteria.medical_safety_score",
            "prohibited_behavior_interception": "safety_capability_criteria.forbidden_behavior_rate",
            "overcommitment_detection": "safety_capability_criteria.over_commitment_detection",
            "risk_avoidance_reminder": "safety_capability_criteria.risk_avoidance_score"
        }
        
        # 检查特殊映射
        if key in special_mappings:
            flat_key = special_mappings[key]
            if flat_key in dimensions:
                return dimensions[flat_key]
        
        # 检查所有可能的键
        for possible_key in possible_keys:
            if possible_key in dimensions:
                return dimensions[possible_key]
        
        # 最后，尝试查找包含该键的部分匹配
        for dim_key in dimensions.keys():
            if key in dim_key:
                return dimensions[dim_key]
        
        return 0.0
    
    def _get_subdimension_comment(self, delta: float, name: str) -> str:
        """根据变化幅度生成子维度点评"""
        if delta > 0.3:
            return f"✅ 显著改进，{name}表现优秀"
        elif delta > 0.1:
            return f"🟡 略有改进，{name}保持关注"
        elif delta < -0.3:
            return f"🔴 显著退化，{name}需要关注"
        elif delta < -0.1:
            return f"🟠 略有下降，{name}建议优化"
        else:
            return f"⚪ 基本稳定，{name}变化不大"
    
    def _get_safety_subdimension_comment(self, delta: float, name: str) -> str:
        """生成安全合规维度的子维度点评（更严格）"""
        if delta > 0.2:
            return f"✅ 安全合规性显著增强，{name}优秀"
        elif delta > 0.05:
            return f"🟡 安全合规性有所提升，{name}良好"
        elif delta < -0.2:
            return f"🔴 **高风险：安全合规性显著下降**，{name}需立即处理"
        elif delta < -0.05:
            return f"🟠 **中风险：安全合规性有所下滑**，{name}建议加强审核"
        else:
            return f"⚪ 安全合规性保持稳定，{name}合规"
    
    def _get_delta_display(self, delta: float) -> str:
        """获取变化的显示格式"""
        if delta > 0.3:
            return f"🟢+{delta:.2f}"
        elif delta > 0.1:
            return f"🟡+{delta:.2f}"
        elif delta < -0.3:
            return f"🔴{delta:.2f}"
        elif delta < -0.1:
            return f"🟠{delta:.2f}"
        else:
            return f"⚪{delta:.2f}"
    
    def _generate_core_dimension_priority_analysis(self, baseline_dims: Dict, current_dims: Dict) -> str:
        """生成核心维度优先级分析"""
        # 计算每个核心维度的总分变化
        dim_scores = {}
        
        for dim_key, dim_config in self.CORE_DIMENSIONS.items():
            dim_total = 0
            subdim_count = 0
            
            for subdim_key, subdim_config in dim_config["subdimensions"].items():
                baseline_score = self._get_dimension_score(baseline_dims, subdim_key, subdim_config["name"])
                current_score = self._get_dimension_score(current_dims, subdim_key, subdim_config["name"])
                
                # 累加子维度得分
                dim_total += current_score
                subdim_count += 1
            
            # 计算平均分
            avg_score = dim_total / max(subdim_count, 1)
            dim_scores[dim_key] = avg_score
        
        # 按重要性排序：安全 > 医疗 > 服务
        priority_order = [
            ("safety_compliance", "🛡️ 安全合规维度", "🔴 P0 (最高)"),
            ("medical_capability", "🏥 医疗能力维度", "🟠 P1 (高)"),
            ("service_capability", "💁 服务能力维度", "🟡 P2 (中)")
        ]
        
        analysis_lines = [
            "| 维度 | 平均分 | 趋势 | 优先级 | 建议 |",
            "|------|--------|------|--------|------|"
        ]
        
        for dim_key, dim_name, priority in priority_order:
            score = dim_scores.get(dim_key, 0)
            
            # 根据分数确定趋势
            if score >= 4.5:
                trend = "📈 优秀"
                suggestion = "继续保持"
            elif score >= 4.0:
                trend = "📈 良好"
                suggestion = "持续优化"
            elif score >= 3.5:
                trend = "➡️ 一般"
                suggestion = "需要改进"
            else:
                trend = "📉 较差"
                suggestion = "重点优化"
            
            analysis_lines.append(
                f"| {dim_name} | {score:.2f} | {trend} | {priority} | {suggestion} |"
            )
        
        return "\n".join(analysis_lines)
