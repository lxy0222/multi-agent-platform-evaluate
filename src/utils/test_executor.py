"""
统一的测试执行器
支持执行不同类型的测试用例（Chat和Workflow）
"""
import json
from typing import Dict, Any
from src.utils.test_case_model import UnifiedTestCase, WorkflowType


class TestExecutor:
    """测试执行器"""
    
    def __init__(self, client_factory, evaluator, history_cache: Dict[str, str] = None):
        """
        初始化执行器
        
        Args:
            client_factory: 客户端工厂函数
            evaluator: 评估器实例
            history_cache: 会话历史缓存
        """
        self.client_factory = client_factory
        self.evaluator = evaluator
        self.history_cache = history_cache or {}
    
    def execute_case(self, case: UnifiedTestCase) -> Dict[str, Any]:
        """
        执行单个测试用例
        
        Args:
            case: 统一格式的测试用例
        
        Returns:
            执行结果字典，包含 response, validation_result 等
        """
        # 获取客户端
        try:
            client = self.client_factory(case.target_agent)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "case_id": case.case_id
            }
        
        # 准备请求参数
        request_params = self._prepare_request(case)
        
        # 执行请求
        workflow_type = case.get_workflow_type()
        if workflow_type == WorkflowType.CHAT:
            response = self._execute_chat(client, request_params, case)
        else:
            response = self._execute_workflow(client, request_params, case)
        
        # 更新会话缓存
        if case.session_key and response.get("conversation_id"):
            self.history_cache[case.session_key] = response["conversation_id"]
        
        # 执行校验
        validation_result = self._validate_response(case, response)
        
        return {
            "success": validation_result["passed"],
            "case_id": case.case_id,
            "request": request_params,
            "response": response,
            "validation": validation_result
        }
    
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
            response = client.send_message(
                query=params["query"],
                inputs=params["inputs"],
                user=params["user"],
                conversation_id=params.get("conversation_id", "")
            )
            return response
        except Exception as e:
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
            # Workflow只需要inputs和user参数
            response = client.run_workflow(
                inputs=params["inputs"],
                user=params["user"]
            )
            return response
        except Exception as e:
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
                return msg_list[0].get("content", "")
        
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
                f"期望 needHuman 为 True，实际为 {need_human}"
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

