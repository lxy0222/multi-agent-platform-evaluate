"""
统一的测试脚本
支持所有类型的测试用例，支持选择性执行
"""
import time
import pytest
import allure
import json
from src.utils.case_loader import load_cases_from_config
from src.utils.test_executor import TestExecutor
from src.utils.logger_config import TestCaseLogger, get_logger


# 全局日志
test_logger = get_logger("test_unified")

# 全局会话缓存
HISTORY_CACHE = {}

# 加载用例
# 从 config/config.yaml 中读取 test_data 配置
test_cases = load_cases_from_config()

test_logger.info(f"加载测试用例数量: {len(test_cases)}")


# ==========================================
# 测试类
# ==========================================
@allure.epic("统一测试框架")
@allure.feature("多智能体回归测试")
class TestUnifiedFramework:
    """统一测试框架"""
    
    @pytest.mark.parametrize("case", test_cases, ids=lambda c: getattr(c, 'case_id', str(c)))
    def test_unified_case(self, case, client_factory, evaluator, results_collector):
        """
        统一的测试用例执行方法
        
        Args:
            case: UnifiedTestCase 实例
            client_factory: 客户端工厂 fixture
            evaluator: 评估器 fixture
            results_collector: 结果收集器 fixture
        """
        # 创建用例日志记录器
        case_logger = TestCaseLogger(case.case_id, test_logger)
        case_logger.start()
        
        # 设置动态标题
        allure.dynamic.title(
            f"[{case.target_agent}] {case.case_id}: {case.scene_description}"
        )
        
        # 添加标签
        for tag in case.tags:
            allure.dynamic.tag(tag)
        
        # 添加优先级
        if case.priority >= 4:
            allure.dynamic.severity(allure.severity_level.CRITICAL)
        elif case.priority >= 3:
            allure.dynamic.severity(allure.severity_level.NORMAL)
        else:
            allure.dynamic.severity(allure.severity_level.MINOR)
        
        # 创建执行器
        executor = TestExecutor(client_factory, evaluator, HISTORY_CACHE)
        
        # ==========================================
        # 步骤1: 准备请求
        # ==========================================
        with allure.step("步骤1: 准备请求参数"):
            # 记录用例信息
            case_info = {
                "用例ID": case.case_id,
                "目标智能体": case.target_agent,
                "场景描述": case.scene_description,
                "用例类型": case.case_type.value,
                "预期动作": case.expected_action,
            }
            test_logger.info(f"[{case.case_id}] 用例信息: {json.dumps(case_info, ensure_ascii=False)}")
            allure.attach(
                json.dumps(case_info, ensure_ascii=False, indent=2),
                name="用例信息",
                attachment_type=allure.attachment_type.JSON
            )
        
        # ==========================================
        # 步骤2: 执行测试
        # ==========================================
        with allure.step(f"步骤2: 执行测试 [{case.get_workflow_type().value}]"):
            result = executor.execute_case(case)
            
            # 记录请求和响应
            case_logger.log_request(result["request"])
            case_logger.log_response(result["response"])
            
            # 记录请求参数
            allure.attach(
                json.dumps(result["request"], ensure_ascii=False, indent=2),
                name="请求参数",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 记录响应结果
            allure.attach(
                json.dumps(result["response"], ensure_ascii=False, indent=2),
                name="响应结果",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 提取AI回复
            ai_reply = executor._extract_reply(result["response"])
            test_logger.info(f"[{case.case_id}] AI回复: {ai_reply[:200]}...")  # 只记录前200字符
            
            metrics = result.get("metrics", {})
            response_time = metrics.get("response_time_ms", 0)
            total_duration = metrics.get("total_duration_ms", 0)
            
            # 显示指标在面板
            allure.dynamic.parameter("Agent首字或推理耗时(ms)", response_time)
            allure.dynamic.parameter("API全链路完整耗时(ms)", total_duration)

            allure.attach(
                f"⏱️ 【耗时性能指标】\nAgent 核心推理响应耗时: {response_time}ms\n平台 API 请求全链路耗时: {total_duration}ms\n\n"
                f"📝 【AI 回复明文提取】\n{ai_reply}",
                name="AI回复及性能指标",
                attachment_type=allure.attachment_type.TEXT
            )
        
        # ==========================================
        # 步骤3: 校验结果
        # ==========================================
        with allure.step("步骤3: 校验结果 (Hard Checks)"):
            validation = result["validation"]
            scoring = result.get("scoring", {})
            
            # 构造直白、清晰的纯文本结构报表
            check_summary = ["【🛡️ 结构与业务硬校验检查点】\n"]
            
            checks = validation.get("checks", [])
            for check in checks:
                check_type = check.get("type", "Unknown Check")
                passed = check.get("passed", False)
                icon = "✅ [通过]" if passed else "❌ [阻断]"
                
                check_summary.append(f"{icon} {check_type}")
                
                req = check.get("requirement")
                if req:
                    check_summary.append(f"    🔸 配置要求: {req}")
                    
                if not passed:
                    errors = check.get("errors", [])
                    for err in errors:
                        check_summary.append(f"    ↳ 💥 {err}")
                        
            allure.attach(
                "\n".join(check_summary) if checks else "当前用例未包含且未执行任何硬校验规则",
                name="📍 [必看] 硬规则检查清单",
                attachment_type=allure.attachment_type.TEXT
            )
            
            # 记录原始日志兜底
            case_logger.log_validation(validation)
            allure.attach(
                json.dumps(validation, ensure_ascii=False, indent=2),
                name="💻 [底层] 校验器生成的 JSON 明细",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 断言 (Fail Fast)
            if not result["success"]:
                error_msg = "\n".join(validation["errors"])
                test_logger.error(f"[{case.case_id}] 测试失败：{error_msg}")
                allure.attach(
                    error_msg,
                    name="失败原因",
                    attachment_type=allure.attachment_type.TEXT
                )

                # 关键修复：在 pytest.fail 之前先收集结果，确保硬校验失败的 case 也能被保存到 baseline
                test_result_data = {
                    "case_id": case.case_id,
                    "target_agent": case.target_agent,
                    "scene_description": case.scene_description,
                    "validation_passed": False,
                    "validation": result.get("validation", {}),  # 包含 checks 列表
                    "hard_score": scoring.get("hard_score", 0),
                    "soft_score": scoring.get("soft_score"),
                    "soft_evaluated": scoring.get("soft_evaluated", False),
                    "soft_pass": scoring.get("soft_pass"),
                    "judge_soft_pass": scoring.get("judge_soft_pass"),
                    "min_score_threshold": case.min_score_threshold,
                    "overall_score": scoring.get("overall_score", 0),
                    "overall_reason": scoring.get("overall_reason", f"硬校验失败：{error_msg}"),
                    "overall_pass": False,
                    "llm_evaluation": {},
                    "dimensions": {},
                    "suggestions": [],
                    "metrics": result.get("metrics", {}),
                    "duration_ms": result.get("metrics", {}).get("total_duration_ms", 0),
                    "response_time_ms": result.get("metrics", {}).get("response_time_ms", 0),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "hard_validation_failed": True,
                    "failure_reason": error_msg
                }

                # 保存到全局收集器
                if case.case_id not in results_collector:
                    results_collector[case.case_id] = []
                results_collector[case.case_id].append(test_result_data)

                pytest.fail(f"用例硬强验失败 (Fail Fast):\n{error_msg}")
            else:
                test_logger.info(f"[{case.case_id}] 硬规则校验通过")
                allure.attach(
                    "✅ 所有校验通过",
                    name="校验结果",
                    attachment_type=allure.attachment_type.TEXT
                )
        
        # 步骤4: LLM 智能评估
        # ==========================================
        with allure.step("步骤4: LLM 智能评估 (Evaluator Agent)"):
            scoring = result.get("scoring", {})
            
            # 安全获取 eval_data
            eval_data = result.get('llm_evaluation') or {}
            
            if eval_data:
                # 记录评估结果
                case_logger.log_evaluation(eval_data)
                
                # ---------------------
                # 构造高颜值的 HTML 可视化报表
                # ---------------------
                pass_status = bool(eval_data.get('pass', eval_data.get('overall_pass', False)))
                score = eval_data.get('overall_score', 0)
                hard_score = scoring.get("hard_score", 0)
                final_score = scoring.get("overall_score", score)
                pass_icon = '✅' if pass_status else '❌'
                
                # HTML 样式预设
                html_report = [
                    "<html>",
                    "<head><style>",
                    "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 20px; color: #333; line-height: 1.6; }",
                    "h2 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 8px; margin-top: 25px; font-size: 1.4em; }",
                    "table { border-collapse: collapse; width: 100%; margin-top: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }",
                    "th, td { border: 1px solid #e0e0e0; text-align: left; padding: 12px; }",
                    "th { background-color: #f8f9fa; font-weight: 600; color: #444; }",
                    "tr:nth-child(even) { background-color: #fbfcff; }",
                    ".score-badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-weight: bold; font-family: monospace; }",
                    ".passed { background-color: #d4edda; color: #155724; }",
                    ".failed { background-color: #f8d7da; color: #721c24; }",
                    ".dim-row { background-color: #f1f3f5 !important; font-weight: bold; }",
                    "</style></head>",
                    "<body>"
                ]
                
                # 最终判决
                overall_class = "passed" if pass_status else "failed"
                html_report.append("<h2>⚖️ 最终判决</h2>")
                html_report.append(f"<p><b>软校验得分:</b> <span class='score-badge {overall_class}'>{score}/100</span> {pass_icon}</p>")
                html_report.append(f"<p><b>硬校验得分:</b> {hard_score}/100</p>")
                html_report.append(f"<p><b>最终综合得分:</b> <b>{final_score}/100</b>（硬/软各 50%）</p>")
                html_report.append(f"<p><b>判决理由:</b> {eval_data.get('overall_reason', '无')}</p>")
                
                # 医疗合规
                medical_analysis = eval_data.get('medical_analysis', {})
                if medical_analysis:
                    html_report.append("<h2>🏥 医疗合规分析</h2>")
                    html_report.append("<ul>")
                    for key, value in medical_analysis.items():
                        status = "✅ 是" if value else "❌ 否"
                        html_report.append(f"<li><b>{key}</b>: {status}</li>")
                    html_report.append("</ul>")
                
                # 维度打分明细
                dimensions = eval_data.get('dimensions', {})
                eval_count = eval_data.get('evaluation_count', 1)
                individual_scores = eval_data.get('individual_scores', [])
                individual_evaluations = eval_data.get('individual_evaluations', [])
                suggestions = eval_data.get('suggestions', [])

                if dimensions:
                    html_report.append("<h2>📊 维度打分明细</h2>")

                    # 如果有多次评估，显示评估统计信息
                    if eval_count > 1:
                        html_report.append(f"<p style='color: #666; font-size: 0.9em;'>ℹ️ 基于 <b>{eval_count}</b> 次独立评估的平均结果，减少 LLM 裁判随机性</p>")

                    html_report.append("<table>")
                    html_report.append("<tr><th width='25%'>考察维度</th><th width='15%'>得分</th><th width='8%'>状态</th><th>详细判决理由</th></tr>")

                    for dim_name, dim_data in dimensions.items():
                        if not isinstance(dim_data, dict):
                            continue
                        d_score = dim_data.get('score', 0)
                        d_pass = dim_data.get('pass', True)
                        d_reason = dim_data.get('reason', '-').replace('\n', '<br>')
                        d_icon = '✅' if d_pass else '❌'
                        css_class = 'passed' if d_pass else 'failed'
                        score_range = dim_data.get('score_range')

                        # 分数显示：如果有波动范围，显示出来
                        score_display = f"{d_score}/100"
                        if score_range and eval_count > 1:
                            score_display += f"<br><span style='font-size:0.8em;color:#888;'>波动：{score_range}</span>"

                        html_report.append(f"<tr class='dim-row'>")
                        html_report.append(f"<td>{dim_name}</td>")
                        html_report.append(f"<td><span class='score-badge {css_class}'>{score_display}</span></td>")
                        html_report.append(f"<td style='text-align:center;'>{d_icon}</td>")
                        html_report.append(f"<td style='font-size: 0.95em; color: #444;'>{d_reason}</td>")
                        html_report.append(f"</tr>")

                        # 子维度层级 (如果存在深度嵌套)
                        for sub_k, sub_v in dim_data.items():
                            if isinstance(sub_v, dict) and 'score' in sub_v:
                                s_score = sub_v.get('score', 0)
                                s_pass = sub_v.get('pass', True)
                                s_icon = '✅' if s_pass else '❌'
                                s_css_class = 'passed' if s_pass else 'failed'
                                s_reason = sub_v.get('reason', '-').replace('\n', '<br>')

                                html_report.append(f"<tr>")
                                html_report.append(f"<td>&nbsp;&nbsp;&nbsp;↳ {sub_k}</td>")
                                html_report.append(f"<td><span class='score-badge {s_css_class}'>{s_score}/100</span></td>")
                                html_report.append(f"<td style='text-align:center;'>{s_icon}</td>")
                                html_report.append(f"<td style='font-size: 0.9em; color: #555;'>{s_reason}</td>")
                                html_report.append(f"</tr>")

                    html_report.append("</table>")

                    # 如果有多次评估，显示各次评估的详细结果（包含子维度）
                    if individual_evaluations and len(individual_evaluations) > 1:
                        html_report.append("<h2 style='margin-top: 25px;'>🔍 各次评估详情</h2>")

                        for eval_item in individual_evaluations:
                            eval_idx = eval_item.get('evaluation_index', 0)
                            eval_score = eval_item.get('overall_score', 0)
                            eval_reason = eval_item.get('overall_reason', '')
                            eval_dims = eval_item.get('dimensions', {})
                            eval_suggestions = eval_item.get('suggestions', [])

                            html_report.append(f"<details style='margin: 10px 0; border: 1px solid #e0e0e0; border-radius: 5px;'>")
                            html_report.append(f"<summary style='cursor: pointer; padding: 10px; background: #f8f9fa; font-weight: bold;'>第 {eval_idx} 次评估：<span class='score-badge {'passed' if eval_score >= 60 else 'failed'}'>{eval_score}/100</span></summary>")
                            html_report.append("<div style='padding: 15px;'>")

                            # 整体理由
                            html_report.append(f"<p style='margin: 10px 0;'><b>评估理由:</b> {eval_reason}</p>")

                            # 子维度详情
                            if eval_dims:
                                html_report.append("<h3 style='font-size: 1.1em; color: #555; margin-top: 15px;'>各维度评分详情</h3>")
                                html_report.append("<table style='font-size: 0.95em;'>")
                                html_report.append("<tr><th width='25%'>维度</th><th width='12%'>得分</th><th>理由</th></tr>")

                                for dim_name, dim_data in eval_dims.items():
                                    if not isinstance(dim_data, dict):
                                        continue
                                    dim_score = dim_data.get('score', 0)
                                    dim_pass = dim_data.get('pass', True)
                                    dim_reason = dim_data.get('reason', '-').replace('\n', '<br>')
                                    dim_icon = '✅' if dim_pass else '❌'
                                    dim_css = 'passed' if dim_pass else 'failed'

                                    html_report.append(f"<tr>")
                                    html_report.append(f"<td>{dim_name}</td>")
                                    html_report.append(f"<td><span class='score-badge {dim_css}'>{dim_score}/100</span> {dim_icon}</td>")
                                    html_report.append(f"<td style='font-size: 0.9em; color: #666;'>{dim_reason}</td>")
                                    html_report.append(f"</tr>")

                                    # 子维度
                                    for sub_k, sub_v in dim_data.items():
                                        if isinstance(sub_v, dict) and 'score' in sub_v:
                                            sub_score = sub_v.get('score', 0)
                                            sub_pass = sub_v.get('pass', True)
                                            sub_reason = sub_v.get('reason', '-').replace('\n', '<br>')
                                            sub_icon = '✅' if sub_pass else '❌'
                                            sub_css = 'passed' if sub_pass else 'failed'

                                            html_report.append(f"<tr style='background: #f9f9f9;'>")
                                            html_report.append(f"<td>&nbsp;&nbsp;&nbsp;↳ {sub_k}</td>")
                                            html_report.append(f"<td><span class='score-badge {sub_css}'>{sub_score}/100</span> {sub_icon}</td>")
                                            html_report.append(f"<td style='font-size: 0.85em; color: #777;'>{sub_reason}</td>")
                                            html_report.append(f"</tr>")

                                html_report.append("</table>")

                            # 改进建议
                            if eval_suggestions:
                                html_report.append("<h3 style='font-size: 1.1em; color: #555; margin-top: 15px;'>改进建议</h3>")
                                html_report.append("<ul>")
                                for suggestion in eval_suggestions:
                                    html_report.append(f"<li style='color: #666;'>{suggestion}</li>")
                                html_report.append("</ul>")

                            html_report.append("</div>")
                            html_report.append("</details>")

                    # 改进建议（汇总）
                    if suggestions:
                        html_report.append("<h2 style='margin-top: 25px;'>💡 改进建议</h2>")
                        html_report.append("<ul>")
                        for suggestion in suggestions:
                            html_report.append(f"<li style='color: #666;'>{suggestion}</li>")
                        html_report.append("</ul>")
                
                # 改进建议
                suggestions = eval_data.get('suggestions', [])
                if suggestions:
                    html_report.append("<h2>💡 改进建议</h2>")
                    html_report.append("<ol>")
                    for suggestion in suggestions:
                        html_report.append(f"<li>{suggestion}</li>")
                    html_report.append("</ol>")
                
                html_report.append("</body></html>")
                
                # 直观附加到面板
                allure.dynamic.parameter("LLM裁判总得分", score)
                
                # 将美化的 HTML 添加为高亮报表附件
                allure.attach(
                    "\n".join(html_report),
                    name="📍 [一目了然] 软规则打分结果报表",
                    attachment_type=allure.attachment_type.HTML
                )
            else:
                skip_msg = (
                    "💡 本用例自动跳过了 LLM 智能打分阶段。\n\n"
                    "跳过原因通常为以下其一：\n"
                    "1. 🛑 Fail Fast 机制：前面的「结构与硬规则」跑出了阻断错误！为了节省 Token 和时间，引擎已强排自动掐断打分。\n"
                    "2. 🔀 转人工防线测试：当前预期必须触发转人工 (`need_human: True`)，纯测底层网关转交，无需分析回复语义！\n"
                    "3. 🚫 手动关闭：你的用例配置里被手动写死了 `need_llm_eval: False`。"
                )
                allure.attach(skip_msg, name="⚡ LLM 智能打分已跳过", attachment_type=allure.attachment_type.TEXT)
            
            # 仍然保留JSON格式用于详细分析
            allure.attach(
                json.dumps(eval_data, ensure_ascii=False, indent=4),
                name="LLM 评估详细结果 (JSON)",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 安全提取基础字段并赋默认值，防止未评估时变量未定义
            eval_dict = eval_data or {}
            soft_score = eval_dict.get("overall_score", 0)
            overall_score = scoring.get("overall_score", soft_score)
            overall_reason = scoring.get("overall_reason", "无评分(用例跳过大模型评估)")
            dimensions = eval_dict.get("dimensions", {})
            pass_status = bool(eval_dict.get("pass", eval_dict.get("overall_pass", False)))
            hard_score = scoring.get("hard_score", 0)
            soft_evaluated = scoring.get("soft_evaluated", False)

            if eval_data:
                allure.dynamic.parameter("LLM评估结论", "✅ 通过" if pass_status else "❌ 未通过")
                allure.dynamic.parameter("Soft Score", soft_score)
            else:
                allure.dynamic.parameter("LLM评估结论", "⏭️ 已跳过")
                allure.dynamic.parameter("Soft Score", "N/A")

            allure.dynamic.parameter("Hard Score", hard_score)
            allure.dynamic.parameter("Overall Score", overall_score)
            
            response_time_ms = result.get("metrics", {}).get("response_time_ms", 0)
            allure.dynamic.parameter("Agent响应时间(ms)", response_time_ms)

            score_summary = [
                "【最终评分汇总】",
                f"硬校验得分: {hard_score}/100",
                f"软校验得分: {soft_score}/100" if soft_evaluated else "软校验得分: 已跳过",
                f"最终综合得分: {overall_score}/100",
                f"最终综合结论: {'✅ 通过' if scoring.get('overall_pass', False) else '❌ 未通过'}",
                f"说明: {overall_reason}"
            ]
            allure.attach(
                "\n".join(score_summary),
                name="📌 最终综合评分",
                attachment_type=allure.attachment_type.TEXT
            )
            
            # 如果配置了子维度，在侧边栏挂载子维度的分数
            for dim_name, dim_data in dimensions.items():
                if isinstance(dim_data, dict):
                    score = dim_data.get("score", 0)
                    passed = dim_data.get("pass")
                    icon = ('✅' if passed else '❌') if passed is not None else ''
                    allure.dynamic.parameter(f"{dim_name}_score", f"{score}{icon}")

            test_logger.info(f"[{case.case_id}] LLM评估完成: Overall Score={overall_score}, Reason={overall_reason}")
            
            # 只有当执行了大模型打分时，才去抛出“评分低于阈值的Warning”
            if eval_data and overall_score < case.min_score_threshold:
                test_logger.warning(f"[{case.case_id}] 评分低于阈值: {overall_score} < {case.min_score_threshold}")
        
        # ==========================================
        # 步骤5: 收集结果到全局收集器
        # ==========================================
        # 记录性能指标
        case_logger.log_metrics(result.get("metrics", {}))
        
        # 获取 LLM 评估结果（可能为 None）
        llm_eval = result.get('llm_evaluation') or {}
        scoring = result.get("scoring", {})

        # 构造完整的测试结果数据
        test_result_data = {
            "case_id": case.case_id,
            "target_agent": case.target_agent,
            "scene_description": case.scene_description,
            "validation_passed": result["success"],
            "validation": result.get("validation", {}),  # 完整的校验结果，包含 checks 列表
            "hard_score": scoring.get("hard_score", 0),
            "soft_score": scoring.get("soft_score"),
            "soft_evaluated": scoring.get("soft_evaluated", False),
            "soft_pass": scoring.get("soft_pass"),
            "judge_soft_pass": scoring.get("judge_soft_pass"),
            "min_score_threshold": case.min_score_threshold,
            "overall_score": scoring.get("overall_score", overall_score),
            "overall_reason": scoring.get("overall_reason", overall_reason),
            "overall_pass": scoring.get("overall_pass", False),
            "llm_evaluation": llm_eval,  # 关键修复：保存完整的 llm_evaluation 对象
            "dimensions": llm_eval.get("dimensions", {}),  # 从 llm_evaluation 获取维度评分（兼容顶层访问）
            "suggestions": llm_eval.get("suggestions", []),  # 改进建议
            "metrics": result.get("metrics", {}),
            "duration_ms": result.get("metrics", {}).get("total_duration_ms", 0),
            "response_time_ms": result.get("metrics", {}).get("response_time_ms", 0),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 保存到全局收集器
        if case.case_id not in results_collector:
            results_collector[case.case_id] = []
        results_collector[case.case_id].append(test_result_data)
        
        # 结束用例日志记录
        case_logger.finish(scoring.get("overall_pass", result["success"]), scoring.get("overall_score", overall_score))
        
        # 缓冲时间(避免请求过快)
        time.sleep(2)
