import re
import json
from src.client.dify_client import DifyClient
from src.utils.logger_config import get_logger

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class Evaluator:
    def __init__(self, judge_api_key=None, model=None, dify_config=None):
        """
        初始化评估器
        :param judge_api_key: 可选。如果不传，则无法使用 soft_check，但可以使用 hard_check
        :param dify_config: 可选。用于配置 Dify 评估器 Agent
        """
        self.client = None
        if judge_api_key and OpenAI:
            self.client = OpenAI(api_key=judge_api_key)
        
        self.dify_evaluator = None
        if dify_config:
            self.dify_evaluator = DifyClient(dify_config)

        self.model = model
        
        # 初始化日志
        self.logger = get_logger("evaluator")

    def hard_check(self, text, expected_type):
        """硬规则检查：不需要 API Key"""
        errors = []
        text = str(text)  # 确保输入是字符串
        
        self.logger.debug(f"开始硬规则检查: expected_type={expected_type}, text_length={len(text)}")

        # 1. 检查思维链
        if "<think>" in text or "</think>" in text:
            errors.append("包含思维链标签 <think>")
            self.logger.warning(f"硬规则检查失败: 包含思维链标签")

        # 2. 检查繁体字/英文 (示例)
        if len(re.findall(r'[a-zA-Z]{15,}', text)) > 0:
            errors.append("包含长英文句子")
            self.logger.warning(f"硬规则检查失败: 包含长英文句子")

        # 3. 预期动作检查
        if expected_type == "Block" and text.strip() != "":
            # 比如 text 为空才算 Block 成功
            # 或者 text 包含 "无需回复"
            pass

        if expected_type == "Delay" and "delay" not in text:
            # 如果不是完全等于 delay，可能需要报错
            pass
        
        result = len(errors) == 0
        self.logger.info(f"硬规则检查完成: {'通过' if result else '失败'}, 错误数={len(errors)}")
        return result, errors

    def llm_evaluate(
        self,
        case_id,
        inputs, 
        actual_output, 
        scene, 
        expected_output=None, 
        context_inputs=None,
        eval_dimensions=None,
        dimension_criteria=None
    ):
        """
        使用 Dify Agent 进行多维度评估
        
        Args:
            case_id: 当前用例ID
            inputs: 用户当前的 query
            actual_output: AI 实际的回复
            scene: 场景描述
            expected_output: 预期的回复或动作，作为"标准答案"参考
            context_inputs: 对话的上下文变量，可能包含关键病历信息
            eval_dimensions: 需要评估的维度列表，如 ["accuracy", "completeness"]
            dimension_criteria: 各维度的评估标准，如 {"accuracy_criteria": "必须正确识别症状"}
        
        Returns:
            {
                "pass": true/false,
                "overall_score": 85,
                "overall_reason": "整体表现良好",
                "dimensions": {
                    "accuracy": {"score": 90, "reason": "..."},
                    "completeness": {"score": 80, "reason": "..."}
                }
            }
        """
        if not self.dify_evaluator:
             self.logger.warning(f"[{case_id}] 跳过LLM评估: 未配置 dify_evaluator")
             return {
                "pass": True,
                "overall_score": 0,
                "overall_reason": "跳过：未配置 dify_evaluator，无法进行 LLM 评分",
                "dimensions": {}
            }
        
        # 构造发给 Dify 评估 Agent 的输入
        agent_inputs = {
            "case_id": case_id,
            "user_query": inputs,
            "ai_response": actual_output,
            "scene": scene,
            "expected_result": expected_output or "",
            "context_inputs": json.dumps(context_inputs or {}, ensure_ascii=False),
            "eval_dimensions": json.dumps(eval_dimensions or ["accuracy", "completeness", "compliance", "tone"], ensure_ascii=False)
        }
        
        # 添加各维度的评估标准
        if dimension_criteria:
            for key, value in dimension_criteria.items():
                if value:  # 只添加非空的标准
                    agent_inputs[key] = value
        
        self.logger.info(f"[{case_id}] 开始LLM评估: scene={scene}")
        self.logger.debug(f"[{case_id}] 评估输入: {json.dumps(agent_inputs, ensure_ascii=False)}")
        
        # 记录超时配置
        if hasattr(self.dify_evaluator, 'timeout'):
            self.logger.debug(f"[{case_id}] Dify 超时设置: {self.dify_evaluator.timeout}秒")
        
        try:
            # 调用 Dify Evaluator
            response = self.dify_evaluator.run_workflow(
                inputs=agent_inputs,
                user="evaluator_bot"
            )
            
            self.logger.debug(f"[{case_id}] Dify响应: {json.dumps(response, ensure_ascii=False)}")
            
            # 解析 Dify 的响应
            raw_outputs = response.get("raw_outputs", "")
            
            evaluation_data = None
            
            # 如果成功解析出数据,进行处理
            if raw_outputs:
                # 需要提取 response 字段
                if isinstance(raw_outputs, dict) and "response" in raw_outputs:
                    evaluation_data = raw_outputs["response"]
                
                result = self._parse_evaluation_result(evaluation_data if evaluation_data else {})
                self.logger.info(
                    f"[{case_id}] LLM评估完成: "
                    f"overall_score={result.get('overall_score', 0)}, "
                    f"pass={result.get('pass', False)}"
                )
                return result
            
            self.logger.error(f"[{case_id}] 无法解析评估结果: {response}")
            return {
                "pass": False, 
                "overall_score": 0, 
                "overall_reason": f"无法解析评估结果: {response}",
                "dimensions": {}
            }
                
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"[{case_id}] LLM评估异常: {error_msg}", exc_info=True)
            
            # 检查是否是超时错误
            is_timeout = "timeout" in error_msg.lower() or "timed out" in error_msg.lower()
            
            if is_timeout:
                timeout_val = getattr(self.dify_evaluator, 'timeout', 60) if self.dify_evaluator else 60
                self.logger.warning(
                    f"[{case_id}] 检测到超时错误！当前超时设置: {timeout_val}秒。"
                    f"建议在配置文件的 judge.dify_config.timeout 中增加超时时间（如 180 或 300）"
                )
                reason = f"Dify 评估超时（{timeout_val}秒），建议增加配置中的 timeout 值"
            else:
                reason = f"评估过程发生错误: {error_msg}"
            
            return {
                "pass": False, 
                "overall_score": 0, 
                "overall_reason": reason,
                "dimensions": {}
            }
    
    def _parse_evaluation_result(self, data: dict) -> dict:
        """
        解析并标准化评估结果
        
        Args:
            data: 从Dify Agent返回的JSON数据
        
        Returns:
            标准化的评估结果
        """
        # 标准化结果结构
        result = {
            "pass": data.get("overall_pass", True),
            "overall_score": data.get("overall_score", 0),
            "overall_reason": data.get("overall_reason", ""),
            "dimensions": {},
            "suggestions": data.get("suggestions", [])
        }
        
        # 解析各维度评分
        dimensions_data = data.get("dimensions", {})
        for dim_name, dim_data in dimensions_data.items():
            if isinstance(dim_data, dict):
                result["dimensions"][dim_name] = {
                    "score": dim_data.get("score", 0),
                    "reason": dim_data.get("reason", ""),
                    "details": dim_data.get("details", "")
                }
            elif isinstance(dim_data, (int, float)):
                # 兼容简化格式
                result["dimensions"][dim_name] = {
                    "score": dim_data,
                    "reason": "",
                    "details": ""
                }
        
        # 如果没有明确的overall_score，根据维度分数计算
        if result["overall_score"] == 0 and result["dimensions"]:
            # 使用配置的权重计算综合分数
            weights = {
                "accuracy": 0.40,
                "completeness": 0.25,
                "compliance": 0.20,
                "tone": 0.15
            }
            
            total_score = 0
            total_weight = 0
            
            for dim_name, dim_data in result["dimensions"].items():
                weight = weights.get(dim_name, 0.25)  # 默认权重0.25
                total_score += dim_data["score"] * weight
                total_weight += weight
            
            if total_weight > 0:
                result["overall_score"] = round(total_score / total_weight, 1)
        
        return result
