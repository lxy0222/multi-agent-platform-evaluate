"""
统一的测试执行器
支持执行不同类型的测试用例(Chat和Workflow)
"""
import json
import time
from typing import Dict, Any, Optional
from src.utils.test_case_model import UnifiedTestCase, WorkflowType
from src.utils.logger_config import get_logger


class TestExecutor:
    """测试执行器"""
    
    def __init__(self, client_factory, evaluator, history_cache: Optional[Dict[str, str]] = None):
        """
        初始化执行器
        
        Args:
            client_factory: 客户端工厂函数
            evaluator: 评估器实例
            history_cache: 会话历史缓存
        """
        self.client_factory = client_factory
        self.evaluator = evaluator
        self.history_cache = history_cache if history_cache is not None else {}
        
        # 初始化日志
        self.logger = get_logger("test_executor")
    
    def execute_case(self, case: UnifiedTestCase) -> Dict[str, Any]:
        """
        执行单个测试用例
        
        Args:
            case: 统一格式的测试用例
        
        Returns:
            执行结果字典,包含 response, validation_result, metrics 等
        """
        self.logger.info(f"开始执行测试用例: {case.case_id}")
        
        # 记录开始时间
        start_time = time.time()
        
        # 获取客户端
        try:
            client = self.client_factory(case.target_agent)
            self.logger.debug(f"[{case.case_id}] 获取客户端成功: target_agent={case.target_agent}")
        except ValueError as e:
            self.logger.error(f"[{case.case_id}] 获取客户端失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "case_id": case.case_id,
                "metrics": self._calculate_error_metrics(time.time() - start_time)
            }
        
        # 准备请求参数
        request_params = self._prepare_request(case)
        self.logger.debug(f"[{case.case_id}] 请求参数: {json.dumps(request_params, ensure_ascii=False)}")
        
        # 执行请求
        workflow_type = case.get_workflow_type()
        request_start = time.time()
        
        if workflow_type == WorkflowType.CHAT:
            self.logger.info(f"[{case.case_id}] 执行Chat请求")
            response = self._execute_chat(client, request_params, case)
        else:
            self.logger.info(f"[{case.case_id}] 执行Workflow请求")
            response = self._execute_workflow(client, request_params, case)
        
        request_duration = (time.time() - request_start) * 1000  # 转换为毫秒
        self.logger.info(f"[{case.case_id}] 请求完成: 耗时={request_duration:.2f}ms")
        
        # 更新会话缓存
        if case.session_key and response.get("conversation_id"):
            self.history_cache[case.session_key] = response["conversation_id"]
            self.logger.debug(f"[{case.case_id}] 更新会话缓存: session_key={case.session_key}")
        
        # 执行校验
        validation_result = self._validate_response(case, response)
        
        # 执行LLM评估（如果配置了评估器）
        llm_evaluation_result = None
        if hasattr(self.evaluator, 'llm_evaluate') and response.get("answer"):
            try:
                llm_evaluation_result = self._perform_llm_evaluation(case, response)
                self.logger.info(f"[{case.case_id}] LLM评估完成: score={llm_evaluation_result.get('overall_score', 0)}")
            except Exception as e:
                self.logger.error(f"[{case.case_id}] LLM评估失败: {str(e)}")
        
        # 计算评估指标
        total_duration = (time.time() - start_time) * 1000
        metrics = self._calculate_metrics(
            case=case,
            response=response,
            validation=validation_result,
            request_duration=request_duration,
            total_duration=total_duration
        )
        
        self.logger.info(
            f"[{case.case_id}] 执行完成: "
            f"success={validation_result['passed']}, "
            f"total_duration={total_duration:.2f}ms"
        )
        
        result = {
            "success": validation_result["passed"],
            "case_id": case.case_id,
            "request": request_params,
            "response": response,
            "validation": validation_result,
            "metrics": metrics,  # 新增:评估指标
            "llm_evaluation": llm_evaluation_result
        }
        
        # 如果LLM评估失败，不影响整体成功状态，但记录在结果中
        if llm_evaluation_result and not llm_evaluation_result.get("pass", True):
            self.logger.warning(f"[{case.case_id}] LLM评估未通过: {llm_evaluation_result.get('overall_reason', '')}")
        
        return result

    
    def _prepare_request(self, case: UnifiedTestCase) -> Dict[str, Any]:
        """准备请求参数"""
        # 复制动态输入，避免修改原始数据
        inputs = case.dynamic_inputs.copy() if case.dynamic_inputs else {}

        # 处理订单详情（工作流类型）- 转为JSON字符串
        if case.order_detail:
            inputs["orderDetail"] = json.dumps(case.order_detail, ensure_ascii=False)

        # 处理聊天历史 - 转为JSON字符串
        if case.chat_history:
            inputs["messages"] = json.dumps(case.chat_history, ensure_ascii=False)
        # if case.materialInfo:
        #     inputs["materialInfo"] = json.dumps(case.materialInfo, ensure_ascii=False)

        # 构造参数
        params = {
            "query": case.input_query or "",
            "inputs": inputs,
            "user": case.get_user_id()
        }

        # 处理会话ID（仅Chat类型需要）
        if case.get_workflow_type() == WorkflowType.CHAT:
            if case.session_key and case.session_key in self.history_cache:
                params["conversation_id"] = self.history_cache[case.session_key]
            elif case.conversation_id:
                params["conversation_id"] = case.conversation_id
            else:
                params["conversation_id"] = ""

        return params
    
    def _execute_chat(
        self, 
        client, 
        params: Dict[str, Any], 
        case: UnifiedTestCase
    ) -> Dict[str, Any]:
        """执行Chat类型的请求"""
        try:
            self.logger.debug(f"[{case.case_id}] 发送Chat消息")
            response = client.send_message(
                query=params["query"],
                inputs=params["inputs"],
                user=params["user"],
                conversation_id=params.get("conversation_id", "")
            )
            self.logger.debug(f"[{case.case_id}] Chat响应成功")
            return response
        except Exception as e:
            self.logger.error(f"[{case.case_id}] Chat请求失败: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed"
            }
    
    def _execute_workflow(
        self,
        client,
        params: Dict[str, Any],
        case: UnifiedTestCase
    ) -> Dict[str, Any]:
        """执行Workflow类型的请求"""
        try:
            self.logger.debug(f"[{case.case_id}] 执行Workflow")
            # Workflow只需要inputs和user参数
            response = client.run_workflow(
                inputs=params["inputs"],
                user=params["user"]
            )
            self.logger.debug(f"[{case.case_id}] Workflow响应成功")
            return response
        except Exception as e:
            self.logger.error(f"[{case.case_id}] Workflow请求失败: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "status": "failed"
            }
    
    def _validate_response(
        self, 
        case: UnifiedTestCase, 
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        校验响应结果
        
        Returns:
            校验结果字典
        """
        validation_result = {
            "passed": True,
            "errors": [],
            "checks": []
        }
        
        # 检查响应状态
        if "error" in response:
            validation_result["passed"] = False
            validation_result["errors"].append(f"请求失败: {response['error']}")
            return validation_result
        
        # 提取AI回复内容
        ai_reply = self._extract_reply(response)
        
        # 执行硬规则检查
        hard_check_passed, hard_errors = self.evaluator.hard_check(
            ai_reply, 
            case.expected_action
        )
        
        validation_result["checks"].append({
            "type": "hard_check",
            "passed": hard_check_passed,
            "errors": hard_errors
        })
        
        if not hard_check_passed:
            validation_result["passed"] = False
            validation_result["errors"].extend(hard_errors)
        
        # 检查转人工（如果需要）
        if case.should_check_human_transfer():
            human_check_result = self._check_human_transfer(response)
            validation_result["checks"].append(human_check_result)
            
            if not human_check_result["passed"]:
                validation_result["passed"] = False
                validation_result["errors"].extend(human_check_result["errors"])
        
        return validation_result
    
    def _extract_reply(self, response: Dict[str, Any]) -> str:
        """从响应中提取AI回复内容"""
        # 尝试从 json_data 中提取
        structured_data = response.get("json_data")
        if isinstance(structured_data, dict):
            msg_list = structured_data.get("messageList", [])
            if msg_list:
                # 拼接所有消息内容
                contents = []
                for msg in msg_list:
                    content = msg.get("content", "")
                    if content:  # 只添加非空内容
                        contents.append(content)
                return "\n\n".join(contents) if contents else ""
        
        # 尝试从 answer 中提取
        return response.get("answer", "")
    
    def _check_human_transfer(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """检查转人工相关字段"""
        result = {
            "type": "human_transfer_check",
            "passed": True,
            "errors": []
        }
        
        structured_data = response.get("json_data", {})
        
        # 检查 needHuman 字段
        need_human = structured_data.get("needHuman")
        if need_human is not True:
            result["passed"] = False
            result["errors"].append(
                f"期望 needHuman 为 True,实际为 {need_human}"
            )
        
        # 检查 messageList 是否为空
        msg_list = structured_data.get("messageList", [])
        for idx, msg in enumerate(msg_list):
            content = msg.get("content")
            if content != "":
                result["passed"] = False
                result["errors"].append(
                    f"messageList 第 {idx + 1} 条消息 content 不为空: '{content}'"
                )
        
        return result
    
    def _calculate_metrics(
        self,
        case: UnifiedTestCase,
        response: Dict[str, Any],
        validation: Dict[str, Any],
        request_duration: float,
        total_duration: float
    ) -> Dict[str, Any]:
        """
        计算评估指标
        
        Args:
            case: 测试用例
            response: API响应
            validation: 校验结果
            request_duration: 请求耗时(ms)
            total_duration: 总耗时(ms)
        
        Returns:
            评估指标字典
        """
        # 提取AI回复
        ai_reply = self._extract_reply(response)
        
        # 基础指标
        metrics = {
            # 性能指标
            "response_time_ms": round(request_duration, 2),
            "total_duration_ms": round(total_duration, 2),
            "is_timeout": request_duration > 5000,  # 5秒超时
            "is_success": "error" not in response,
            
            # 准确性指标
            "validation_passed": validation["passed"],
            "hard_check_passed": any(
                check["type"] == "hard_check" and check["passed"] 
                for check in validation.get("checks", [])
            ),
            "expected_action_match": validation["passed"],
            
            # 质量指标
            "reply_length": len(ai_reply),
            "is_empty_reply": len(ai_reply.strip()) == 0,
            "has_think_tag": "<think>" in ai_reply or "</think>" in ai_reply,
            
            # 业务指标
            "human_transfer_required": case.should_check_human_transfer(),
            "human_transfer_correct": False,
        }
        
        # 检查转人工准确性
        if case.should_check_human_transfer():
            human_check = next(
                (check for check in validation.get("checks", []) 
                 if check["type"] == "human_transfer_check"),
                None
            )
            if human_check:
                metrics["human_transfer_correct"] = human_check["passed"]
        
        # 解析JSON结构化数据
        if isinstance(response.get("json_data"), dict):
            json_data = response["json_data"]
            metrics["has_structured_output"] = True
            metrics["need_human"] = json_data.get("needHuman", False)
        else:
            metrics["has_structured_output"] = False
        
        return metrics
    
    def _perform_llm_evaluation(
        self, 
        case: UnifiedTestCase, 
        response: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行LLM评估
        
        Args:
            case: 测试用例
            response: API响应
            
        Returns:
            LLM评估结果
        """
        # 提取AI回复
        ai_reply = self._extract_reply(response)
        
        # 获取测试用例的增强评估输入
        eval_inputs = case.get_enhanced_evaluation_inputs()
        
        # 准备评估参数
        eval_params = {
            "case_id": case.case_id,
            "inputs": case.input_query,
            "actual_output": ai_reply,
            "scene": case.scene_description,
            "expected_output": case.expected_result,
            "context_inputs": case.dynamic_inputs,
            "eval_dimensions": eval_inputs.get("eval_dimensions", []),
            "dimension_criteria": eval_inputs.get("dimension_criteria", {})
        }
        
        # 如果有测试用例特定的评估指标，添加到评估参数中
        if eval_inputs.get("test_case_specific_metrics"):
            eval_params["test_case_specific_metrics"] = eval_inputs["test_case_specific_metrics"]
        
        # 如果有维度权重，也传递给评估器
        if eval_inputs.get("dimension_weights"):
            eval_params["dimension_weights"] = eval_inputs["dimension_weights"]
        
        # 调用评估器
        if hasattr(self.evaluator, 'medical_llm_evaluate'):
            # 使用医疗评估器
            return self.evaluator.medical_llm_evaluate(**eval_params)
        else:
            # 使用基础评估器
            return self.evaluator.llm_evaluate(**eval_params)
    
    def _calculate_error_metrics(self, duration: float) -> Dict[str, Any]:
        """计算错误情况下的指标"""
        return {
            "response_time_ms": round(duration * 1000, 2),
            "total_duration_ms": round(duration * 1000, 2),
            "is_timeout": False,
            "is_success": False,
            "validation_passed": False,
            "hard_check_passed": False,
            "expected_action_match": False,
            "reply_length": 0,
            "is_empty_reply": True,
            "has_think_tag": False,
            "human_transfer_required": False,
            "human_transfer_correct": False,
            "has_structured_output": False
        }

