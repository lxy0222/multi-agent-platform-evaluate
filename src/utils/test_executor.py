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
        if workflow_type == WorkflowType.CHAT:
            self.logger.info(f"[{case.case_id}] 执行Chat请求")
            response = self._execute_chat(client, request_params, case)
        else:
            self.logger.info(f"[{case.case_id}] 执行Workflow请求")
            response = self._execute_workflow(client, request_params, case)

        # 提取从内层函数传上来的“纯粹收发包掐表耗时”，剥离掉所有打印日志的 IO 时间
        request_duration = response.get('_api_latency_ms', (time.time() - start_time) * 1000)
        self.logger.info(f"[{case.case_id}] 请求完成: 精准纯净耗时(RTT)={request_duration:.2f}ms")
        

        
        # 执行校验
        validation_result = self._validate_response(case, response)
        
        # 判断是否需要执行 LLM 软打分评估
        llm_evaluation_result = None
        if hasattr(self.evaluator, 'llm_evaluate') and response.get("answer"):
            if self._should_run_llm_eval(case, validation_result):
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

    
    def _should_run_llm_eval(self, case: UnifiedTestCase, validation_result: Dict) -> bool:
        """判断当前用例是否需要走大模型软打分评估阶段"""
        ground_truth = case.ground_truth or {}
        
        # 1. 显式开关：如果指定 need_llm_eval = False，一票否决
        # 默认情况下，只要不明确写 False，都默认放行去跑大模型评分（因为 Dify 裁判本身自带默认打分Prompt）
        if ground_truth.get("need_llm_eval") is False:
            self.logger.info(f"[{case.case_id}] 配置显式跳过 LLM 大模型评分阶段")
            return False
            
        # 2. 核心业务阻断判断：如果用例的预期行为就是为了测试“触发转人工接管系统”，
        # 那么此时 AI 只是吐出一句敷衍的制式话术甚至不吐文本，去打分毫无意义，智能跳出。
        system_state = ground_truth.get("hard_rules", {}).get("system_state", {})
        if system_state.get("need_human") is True:
            self.logger.info(f"[{case.case_id}] 当前为转人工防线测试用例，无需主观打分，自动跳过")
            return False
            
        # 3. Fail Fast 智能止损机制：前面的结构/拦截硬校验如果没过，就不用跑 LLM 写小作文了
        if not validation_result.get("passed", False):
            self.logger.warning(f"[{case.case_id}] 底层硬校验阻断连接 (Fail Fast)，及时中止后续 LLM 打分资源消耗")
            return False
            
        return True

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
            if case.conversation_id:
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
            # 记录详细的请求信息
            self.logger.info(f"[{case.case_id}] 🚀 发送Chat请求")
            self.logger.info(f"[{case.case_id}] 📋 请求概要:")
            self.logger.info(f"[{case.case_id}]   - 目标平台: {case.target_agent}")
            self.logger.info(f"[{case.case_id}]   - 用户ID: {params['user']}")
            self.logger.info(f"[{case.case_id}]   - 会话ID: {params.get('conversation_id', '(新会话)')}")
            
            # 记录query内容
            if params.get("query"):
                query_str = str(params["query"])
                if len(query_str) > 300:
                    self.logger.info(f"[{case.case_id}]   - query: {query_str[:150]}...[{len(query_str)-150}字符已省略]")
                else:
                    self.logger.info(f"[{case.case_id}]   - query: {query_str}")
            
            # 记录inputs参数
            if params.get("inputs"):
                inputs_log = {}
                for key, value in params["inputs"].items():
                    if isinstance(value, str) and len(value) > 200:
                        inputs_log[key] = f"{value[:100]}...[{len(value)-100}字符已省略]"
                    elif key in ['api_key', 'secret', 'password', 'token', 'bearer_token']:
                        inputs_log[key] = "[敏感信息已隐藏]"
                    else:
                        inputs_log[key] = value
                self.logger.info(f"[{case.case_id}]   - inputs: {json.dumps(inputs_log, ensure_ascii=False)}")
            
            _api_start = time.time()
            response = client.send_message(
                query=params["query"],
                inputs=params["inputs"],
                user=params["user"],
                conversation_id=params.get("conversation_id", "")
            )
            # 在收到返回的瞬间记录结束时间，完全剥离前后的框架打桩耗时
            response['_api_latency_ms'] = (time.time() - _api_start) * 1000
            
            # 记录响应信息
            if response.get("status") == "success":
                self.logger.info(f"[{case.case_id}] ✅ Chat请求成功")
                self.logger.info(f"[{case.case_id}] 📊 响应概要:")
                self.logger.info(f"[{case.case_id}]   - 状态: {response.get('status')}")
                self.logger.info(f"[{case.case_id}]   - task_id: {response.get('task_id', 'N/A')}")
                self.logger.info(f"[{case.case_id}]   - conversation_id: {response.get('conversation_id', 'N/A')}")
                
                # 记录answer内容
                answer = response.get("answer", "")
                if answer:
                    if len(str(answer)) > 500:
                        self.logger.info(f"[{case.case_id}]   - answer: {str(answer)[:200]}...[{len(str(answer))-200}字符已省略]")
                    else:
                        self.logger.info(f"[{case.case_id}]   - answer: {answer}")
            else:
                self.logger.warning(f"[{case.case_id}] ⚠️  Chat请求异常: {response.get('status', 'unknown')}")
                self.logger.warning(f"[{case.case_id}]   - 错误信息: {response.get('answer', 'No error message')}")
            
            return response
        except Exception as e:
            self.logger.error(f"[{case.case_id}] ❌ Chat请求失败: {str(e)}", exc_info=True)
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
            # 记录详细的Workflow请求信息
            self.logger.info(f"[{case.case_id}] 🚀 发送Workflow请求")
            self.logger.info(f"[{case.case_id}] 📋 请求概要:")
            self.logger.info(f"[{case.case_id}]   - 目标平台: {case.target_agent}")
            self.logger.info(f"[{case.case_id}]   - 用户ID: {params['user']}")
            self.logger.info(f"[{case.case_id}]   - 请求类型: Workflow")
            
            # 记录inputs参数
            if params.get("inputs"):
                inputs_log = {}
                for key, value in params["inputs"].items():
                    if isinstance(value, str) and len(value) > 200:
                        inputs_log[key] = f"{value[:100]}...[{len(value)-100}字符已省略]"
                    elif key in ['api_key', 'secret', 'password', 'token', 'bearer_token']:
                        inputs_log[key] = "[敏感信息已隐藏]"
                    else:
                        inputs_log[key] = value
                self.logger.info(f"[{case.case_id}]   - inputs: {json.dumps(inputs_log, ensure_ascii=False)}")
            
            # Workflow只需要inputs和user参数
            _api_start = time.time()
            response = client.run_workflow(
                inputs=params["inputs"],
                user=params["user"]
            )
            # 记录Workflow发包返回纯净耗时
            response['_api_latency_ms'] = (time.time() - _api_start) * 1000
            
            # 记录响应信息
            if response.get("status") == "success":
                self.logger.info(f"[{case.case_id}] ✅ Workflow请求成功")
                self.logger.info(f"[{case.case_id}] 📊 响应概要:")
                self.logger.info(f"[{case.case_id}]   - 状态: {response.get('status')}")
                self.logger.info(f"[{case.case_id}]   - workflow_run_id: {response.get('workflow_run_id', 'N/A')}")
                self.logger.info(f"[{case.case_id}]   - task_id: {response.get('task_id', 'N/A')}")
                
                # 记录answer内容
                answer = response.get("answer", "")
                if answer:
                    if len(str(answer)) > 500:
                        self.logger.info(f"[{case.case_id}]   - answer: {str(answer)[:200]}...[{len(str(answer))-200}字符已省略]")
                    else:
                        self.logger.info(f"[{case.case_id}]   - answer: {answer}")
            else:
                self.logger.warning(f"[{case.case_id}] ⚠️  Workflow请求异常: {response.get('status', 'unknown')}")
                self.logger.warning(f"[{case.case_id}]   - 错误信息: {response.get('answer', 'No error message')}")
            
            return response
        except Exception as e:
            self.logger.error(f"[{case.case_id}] ❌ Workflow请求失败: {str(e)}", exc_info=True)
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
        
        hard_rules = case.ground_truth.get("hard_rules", {})
        
        # 1. 解析结果校验
        if hard_rules.get("require_valid_json"):
            json_errs = []
            if not response.get("json_data"):
                json_errs.append("要求返回有效的结构化 JSON 数据，但解析为空或失败")
            validation_result["checks"].append({
                "type": "JSON结果解析约束 (require_valid_json)",
                "passed": len(json_errs) == 0,
                "requirement": "True",
                "errors": json_errs
            })
            
        # 2. 违禁词汇检测
        forbidden_words = hard_rules.get("forbidden_words", [])
        if forbidden_words:
            forb_errs = []
            for word in forbidden_words:
                if word in ai_reply:
                    forb_errs.append(f"合规拦截：回复中包含了绝对禁用词汇 '{word}'")
            validation_result["checks"].append({
                "type": "业务违禁词拦截 (forbidden_words)",
                "passed": len(forb_errs) == 0,
                "requirement": str(forbidden_words),
                "errors": forb_errs
            })
                
        # 3. 必须包含的语义核心词
        must_include = hard_rules.get("must_include_words", hard_rules.get("must_include", []))
        if must_include:
            inc_errs = []
            for word in must_include:
                if word not in ai_reply:
                    inc_errs.append(f"语义缺失：回复未命中必须提及的关键词 '{word}'")
            validation_result["checks"].append({
                "type": "必含核心语义词检测 (must_include)",
                "passed": len(inc_errs) == 0,
                "requirement": str(must_include),
                "errors": inc_errs
            })

        # 工具调用判断
        tool_calling = hard_rules.get("tool_calling", {})
        if tool_calling:
            tool_errs = []
            must_call = tool_calling.get("must_call_tool")
            must_not_call = tool_calling.get("must_not_call_tool")
            
            # 使用全量字典字符串匹配的方式兜底查找工具调用特征（Dify底层通常会将工具动作记在JSON某处）
            response_json_str = json.dumps(response, ensure_ascii=False)
            
            if must_call and must_call not in response_json_str:
                tool_errs.append(f"工具调用错误：要求必须调用工具 '{must_call}'，但在执行链路中未检测到调用记录")
                
            if must_not_call and must_not_call in response_json_str:
                tool_errs.append(f"工具调用错误：要求绝对禁止调用工具 '{must_not_call}'，但实际被触发了")
                
            validation_result["checks"].append({
                "type": "工具插件调用断言 (tool_calling)",
                "passed": len(tool_errs) == 0,
                "requirement": str(tool_calling),
                "errors": tool_errs
            })

        # 新增：正则校验（多用于特定外链或格式匹配）
        expected_link = hard_rules.get("expected_link_match")
        if expected_link:
            import re
            link_errs = []
            if not re.search(expected_link, ai_reply):
                link_errs.append(f"正则/外链匹配失败：回复中未命中特定匹配模式 '{expected_link}'")
            validation_result["checks"].append({
                "type": "正则及外链校验 (expected_link_match)",
                "passed": len(link_errs) == 0,
                "requirement": expected_link,
                "errors": link_errs
            })

        # 4. 执行状态树断言
        system_state = hard_rules.get("system_state", {})
        if system_state:
            state_errs = []
            msgs = response.get("json_data", {}).get("messageList", [])
            
            # 校验需转人工标志
            if "need_human" in system_state:
                is_human = response.get("json_data", {}).get("needHuman") is True
                if is_human != system_state["need_human"]:
                    state_errs.append(f"底层状态错误：人工接管状态实际为 {is_human}，但预期应为 {system_state['need_human']}")
            
            # 校验消息队列是否放空（特定动作要求）
            if system_state.get("messageList_empty") is True:
                for msg in msgs:
                    if msg.get("content"):
                        state_errs.append(f"底层状态错误：预期 messageList 内容字段必须为空，但存在输出: '{msg.get('content')}'")
            
            # 校验是否发送了卡片
            if system_state.get("has_mini_program") is True:
                has_mp = any(
                    msg.get("msgType", "").lower() in ["miniprogram", "mini_program"] or 
                    "appid" in str(msg.get("content", "")).lower() 
                    for msg in msgs
                )
                if not has_mp:
                    state_errs.append("转化漏斗错误：预期应该下发小程序卡片(has_mini_program=True)，但未从消息流检测到卡片特征")

            # 校验是否发送了图片或海报图片
            if system_state.get("has_image_poster") is True:
                has_img = any(
                    msg.get("msgType", "").lower() == "image" or 
                    (".jpg" in str(msg.get("content", "")).lower() or ".png" in str(msg.get("content", "")).lower()) 
                    for msg in msgs
                )
                if not has_img:
                    state_errs.append("动作断言错误：预期应该下发图片海报(has_image_poster=True)，但未从消息流检测到图片类型")

            validation_result["checks"].append({
                "type": "系统流转状态检测 (system_state)",
                "passed": len(state_errs) == 0,
                "requirement": str(system_state),
                "errors": state_errs
            })
        
        # 5. 这里的硬校验为所有用例common check list，包含那种英文、思维链校验
        old_hard_check_passed, old_hard_errors = self.evaluator.hard_check(
            ai_reply, 
            case.expected_action
        )
        validation_result["checks"].append({
            "type": "系统底层基础校验 (System Target)",
            "passed": old_hard_check_passed,
            "requirement": f"expected_action={case.expected_action}",
            "errors": old_hard_errors
        })
        
        # 汇总：把所有 checks 里没过关的 error 都塞回全局 passed
        for chk in validation_result["checks"]:
            if not chk.get("passed"):
                validation_result["passed"] = False
                validation_result["errors"].extend(chk.get("errors", []))
        
        # 兼容原本独有的转人工检查配置
        if case.should_check_human_transfer() and "need_human" not in system_state:
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
        
        # 取消校验 messageList 的内容必须为空的逻辑
        # msg_list = structured_data.get("messageList", [])
        # for idx, msg in enumerate(msg_list):
        #     content = msg.get("content")
        #     if content != "":
        #         result["passed"] = False
        #         result["errors"].append(
        #             f"messageList 第 {idx + 1} 条消息 content 不为空: '{content}'"
        #         )
        
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
        
        # 提取转人工相关参数（如果存在）
        human_transfer_data = None
        json_data = response.get("json_data")
        if isinstance(json_data, dict):
            need_human = json_data.get("needHuman")
            human_reason = json_data.get("humanReason")
            message_list = json_data.get("messageList")
            # 只要有任意一个字段存在，就构造 human_transfer_data
            if need_human is not None or human_reason is not None or message_list is not None:
                human_transfer_data = {
                    "needHuman": need_human,
                    "humanReason": human_reason,
                    "messageList": message_list or []
                }
                self.logger.info(
                    f"[{case.case_id}] 检测到转人工参数: needHuman={need_human}, "
                    f"humanReason={human_reason}"
                )

        # 提取软校验预期，以无感拼接到 expected_output 传给 Dify Agent
        soft_rules = case.ground_truth.get("soft_rules", {})
        expected_output_val = ""
        if soft_rules:
            if list(soft_rules.keys()) == ["expected_result"]:
                expected_output_val = soft_rules["expected_result"]
            else:
                # 包装为友好的强提示格式返回给 Dify Prompt 的 {{expected_result}}
                expected_output_val = (
                    "【当前用例专属打分要求 (Local Soft Rules)】\n"
                    "请额外结合以下给出的这道题的专属客观校验预期对 AI 回复进行打分：\n"
                    f"{json.dumps(soft_rules, ensure_ascii=False, indent=2)}"
                )

        # 准备评估参数
        eval_params = {
            "case_id": case.case_id,
            "inputs": case.input_query,
            "actual_output": ai_reply,
            "scene": case.scene_description,
            "expected_output": expected_output_val,
            "context_inputs": case.dynamic_inputs,
            "eval_dimensions": eval_inputs.get("eval_dimensions", []),
            "dimension_criteria": eval_inputs.get("dimension_criteria", {}),
            "human_transfer_data": human_transfer_data
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

