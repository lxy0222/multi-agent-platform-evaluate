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
    
    @pytest.mark.parametrize("case", test_cases, ids=lambda c: c.case_id)
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
                "会话标识": case.session_key,
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
            allure.attach(
                ai_reply,
                name="AI回复内容",
                attachment_type=allure.attachment_type.TEXT
            )
        
        # ==========================================
        # 步骤3: 校验结果
        # ==========================================
        with allure.step("步骤3: 校验结果"):
            validation = result["validation"]
            
            # 记录校验结果
            case_logger.log_validation(validation)
            
            # 记录校验详情
            allure.attach(
                json.dumps(validation, ensure_ascii=False, indent=2),
                name="校验详情",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 断言
            if not result["success"]:
                error_msg = "\n".join(validation["errors"])
                test_logger.error(f"[{case.case_id}] 测试失败: {error_msg}")
                allure.attach(
                    error_msg,
                    name="失败原因",
                    attachment_type=allure.attachment_type.TEXT
                )
                pytest.fail(f"测试失败:\n{error_msg}")
            else:
                test_logger.info(f"[{case.case_id}] 硬规则校验通过")
                allure.attach(
                    "✅ 所有校验通过",
                    name="校验结果",
                    attachment_type=allure.attachment_type.TEXT
                )
        
        # ==========================================
        # 步骤4: LLM 智能评估
        # ==========================================
        with allure.step("步骤4: LLM 智能评估 (Evaluator Agent)"):
            
            # 记录评估结果
            case_logger.log_evaluation(result['llm_evaluation'])
            
            # 将评分结果写入报告 - 使用层级结构显示
            eval_data = result['llm_evaluation']
            
            # 创建评估结果摘要
            with allure.step("📊 评估结果摘要"):
                # 处理overall_pass，可能是布尔值或字符串'pass'/'fail'
                overall_pass = eval_data.get('overall_pass', False)
                if isinstance(overall_pass, str):
                    pass_status = overall_pass.lower() == 'pass'
                else:
                    pass_status = bool(overall_pass)
                
                allure.attach(
                    f"总体评分: {eval_data.get('overall_score', 0)}/100\n"
                    f"通过状态: {'✅ 通过' if pass_status else '❌ 未通过'}\n"
                    f"评估理由: {eval_data.get('overall_reason', '无')}",
                    name="摘要信息",
                    attachment_type=allure.attachment_type.TEXT
                )
            
            # 显示医疗分析部分（如果有）
            medical_analysis = eval_data.get('medical_analysis', {})
            if medical_analysis:
                with allure.step("🏥 医疗分析"):
                    med_analysis_text = ""
                    for key, value in medical_analysis.items():
                        status = "✅ 是" if value else "❌ 否"
                        med_analysis_text += f"{key}: {status}\n"
                    allure.attach(
                        med_analysis_text,
                        name="医疗分析详情",
                        attachment_type=allure.attachment_type.TEXT
                    )
            
            # 显示各维度评分 - 使用层级结构
            dimensions = eval_data.get('dimensions', {})
            if dimensions:
                with allure.step("📈 维度评估详情"):
                    # 为每个主要维度创建子步骤
                    for dim_name, dim_data in dimensions.items():
                        if isinstance(dim_data, dict):
                            with allure.step(f"{dim_name}"):
                                # 显示该维度的所有子维度
                                for sub_dim_name, sub_dim_data in dim_data.items():
                                    if isinstance(sub_dim_data, dict) and 'score' in sub_dim_data:
                                        sub_dim_score = sub_dim_data.get('score', 0)
                                        sub_dim_reason = sub_dim_data.get('reason', '')
                                        sub_dim_details = sub_dim_data.get('details', '')
                                        
                                        with allure.step(f"{sub_dim_name}: {sub_dim_score}/10"):
                                            # 构建子维度详情，直接显示三个值
                                            sub_dim_content = f"score: {sub_dim_score}/10\n\n"
                                            
                                            if sub_dim_reason:
                                                sub_dim_content += f"reason:\n{sub_dim_reason}\n\n"
                                            
                                            if sub_dim_details:
                                                sub_dim_content += f"details:\n{sub_dim_details}"
                                            
                                            # 附加子维度信息
                                            allure.attach(
                                                sub_dim_content,
                                                name="子维度详情",
                                                attachment_type=allure.attachment_type.TEXT
                                            )
            
            # 显示改进建议（如果有）
            suggestions = eval_data.get('suggestions', [])
            if suggestions:
                with allure.step(f"💡 改进建议 ({len(suggestions)}条)"):
                    suggestions_text = ""
                    for i, suggestion in enumerate(suggestions, 1):
                        suggestions_text += f"{i}. {suggestion}\n"
                    
                    allure.attach(
                        suggestions_text,
                        name="改进建议详情",
                        attachment_type=allure.attachment_type.TEXT
                    )
            
            # 仍然保留JSON格式用于详细分析
            allure.attach(
                json.dumps(eval_data, ensure_ascii=False, indent=4),
                name="LLM 评估详细结果 (JSON)",
                attachment_type=allure.attachment_type.JSON
            )
            
            overall_score = result['llm_evaluation'].get("overall_score", 0)
            overall_reason = result['llm_evaluation'].get("overall_reason", "无")
            dimensions = result['llm_evaluation'].get("dimensions", {})
            
            # 在报告摘要中显示分数
            allure.dynamic.parameter("Overall Score", overall_score)
            
            # 显示各维度评分
            for dim_name, dim_data in dimensions.items():
                if isinstance(dim_data, dict):
                    allure.dynamic.parameter(f"{dim_name}_score", dim_data.get("score", 0))
            
            test_logger.info(f"[{case.case_id}] LLM评估完成: Overall Score={overall_score}, Reason={overall_reason}")
            
            # 检查是否达到阈值
            if overall_score < case.min_score_threshold:
                test_logger.warning(f"[{case.case_id}] 评分低于阈值: {overall_score} < {case.min_score_threshold}")
        
        # ==========================================
        # 步骤5: 收集结果到全局收集器
        # ==========================================
        # 记录性能指标
        case_logger.log_metrics(result.get("metrics", {}))
        
        # 构造完整的测试结果数据
        test_result_data = {
            "case_id": case.case_id,
            "target_agent": case.target_agent,
            "scene_description": case.scene_description,
            "validation_passed": result["success"],
            "overall_score": overall_score,
            "overall_reason": overall_reason,
            "overall_pass": result['llm_evaluation'].get("pass", False),
            "dimensions": dimensions,  # 新增：各维度详细评分
            "suggestions": result['llm_evaluation'].get("suggestions", []),  # 新增：改进建议
            "metrics": result.get("metrics", {}),
            "duration_ms": result.get("metrics", {}).get("total_duration_ms", 0),
            "response_time_ms": result.get("metrics", {}).get("response_time_ms", 0),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 保存到全局收集器
        results_collector[case.case_id] = test_result_data
        
        # 结束用例日志记录
        case_logger.finish(result["success"], overall_score)
        
        # 缓冲时间(避免请求过快)
        time.sleep(2)

