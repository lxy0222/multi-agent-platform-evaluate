import re
import json
from typing import Optional
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
        dimension_criteria=None,
        dimension_weights=None,
        test_case_specific_metrics=None,
        human_transfer_data=None,
        grading_criteria=None
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
             dimension_criteria: 各维度的评估标准，如 {"accuracy": "必须正确识别症状"}
             dimension_weights: 各维度权重，如 {"accuracy": 0.4, "completeness": 0.3}
             test_case_specific_metrics: 测试用例特定的补充评估指标
         
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
            "eval_dimensions": json.dumps(eval_dimensions or [], ensure_ascii=False)
        }
        
        # 注入转人工参数：合并为单个 JSON 字符串字段，Dify 只需一个输入变量
        if human_transfer_data:
            human_transfer_info = {
                "needHuman": human_transfer_data.get("needHuman"),
                "humanReason": human_transfer_data.get("humanReason") or "",
                "messageList": human_transfer_data.get("messageList") or []
            }
            agent_inputs["human_transfer_info"] = json.dumps(human_transfer_info, ensure_ascii=False)
            self.logger.info(
                f"[{case_id}] 注入转人工参数(human_transfer_info): "
                f"needHuman={human_transfer_info['needHuman']}, "
                f"humanReason={human_transfer_info['humanReason']}"
            )

        # 注入评分等级标准（如果有）
        if grading_criteria:
            agent_inputs["grading_criteria"] = grading_criteria
            self.logger.debug(f"[{case_id}] 注入评分等级标准")
        
        # 添加各维度的评估标准（支持新格式）
        if dimension_criteria:
            # 新格式：{"accuracy": "必须正确识别症状"}
            # 旧格式：{"accuracy_criteria": "必须正确识别症状"}
            for key, value in dimension_criteria.items():
                if value:  # 只添加非空的标准
                    if "_criteria" in key:
                        # 旧格式，直接添加
                        agent_inputs[key] = value
                    else:
                        # 新格式，转换为旧格式
                        agent_inputs[f"{key}_criteria"] = value
        
        # 添加维度权重（如果有）
        if dimension_weights:
            agent_inputs["dimension_weights"] = json.dumps(dimension_weights, ensure_ascii=False)
        
        # 添加测试用例特定的评估指标（如果有）
        if test_case_specific_metrics:
            agent_inputs["test_case_specific_metrics"] = json.dumps(test_case_specific_metrics, ensure_ascii=False)
        
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
                evaluation_data = self._extract_evaluation_json(raw_outputs)

                self.logger.info(
                    f"[{case_id}] LLM评估完成: "
                    f"overall_score={evaluation_data.get('overall_score', 0)}, "
                    f"pass={evaluation_data.get('pass', False)}"
                )
                return evaluation_data
            
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
    
    def _normalize_boolean(self, value) -> bool:
        """Normalize boolean-like values from various formats."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            value_lower = value.strip().lower()
            true_values = {
                "true", "1", "yes", "y", "pass", "passed", "success", "ok",
                "是", "通过", "成功"
            }
            false_values = {
                "false", "0", "no", "n", "fail", "failed", "error",
                "否", "不通过", "失败"
            }
            if value_lower in true_values:
                return True
            if value_lower in false_values:
                return False
        self.logger.warning(
            f"无法解析布尔值: {value} (type={type(value)}), defaulting to True"
        )
        return True

    def _normalize_score(self, value) -> float:
        """Normalize score values to float in [0, 100]."""
        if value is None:
            return 0.0
        try:
            if isinstance(value, (int, float)):
                score = float(value)
            elif isinstance(value, str):
                cleaned = value.strip()
                cleaned = cleaned.replace("%", "").replace("分", "")
                match = re.search(r"-?\d+(\.\d+)?", cleaned)
                if not match:
                    raise ValueError(f"no numeric value in '{value}'")
                score = float(match.group(0))
            else:
                raise ValueError(f"unsupported type: {type(value)}")
        except Exception as exc:
            self.logger.warning(f"分数转换失败: {value}, error={exc}")
            return 0.0
        if score < 0:
            return 0.0
        if score > 100:
            return 100.0
        return score

    def _extract_evaluation_json(self, data):
        """Extract evaluation dict from nested or noisy structures."""
        if data is None:
            return {}
        if isinstance(data, str):
            try:
                parsed = json.loads(data)
                return self._extract_evaluation_json(parsed)
            except Exception:
                # best-effort: try to parse a JSON object substring
                start = data.find("{")
                end = data.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        parsed = json.loads(data[start:end + 1])
                        return self._extract_evaluation_json(parsed)
                    except Exception:
                        return {}
                return {}
        if isinstance(data, list):
            for item in data:
                found = self._extract_evaluation_json(item)
                if found:
                    return found
            return {}
        if not isinstance(data, dict):
            return {}

        known_keys = {"overall_pass", "overall_score", "overall_reason", "dimensions", "suggestions"}
        if any(k in data for k in known_keys):
            return data

        if "properties" in data and isinstance(data.get("properties"), dict):
            return self._extract_evaluation_json(data["properties"])
        if "response" in data and isinstance(data.get("response"), dict):
            return self._extract_evaluation_json(data["response"])
        if "entry" in data and isinstance(data.get("entry"), dict):
            return self._extract_evaluation_json(data["entry"])

        for value in data.values():
            found = self._extract_evaluation_json(value)
            if found:
                return found
        return {}

    def _extract_structured_data(self, data: dict) -> dict:
        """Extract structured evaluation data from flattened/noisy dicts."""
        if not isinstance(data, dict):
            return {}

        cleaned = {}
        key_fields = {
            "overall_pass", "overall_score", "overall_reason",
            "dimensions", "suggestions", "entry", "properties"
        }

        def normalize_key(key: str):
            if not isinstance(key, str):
                return key
            for target in ["overall_pass", "overall_score", "overall_reason", "dimensions", "suggestions"]:
                if target in key:
                    return target
            return key

        def is_schema_dict(value):
            if not isinstance(value, dict):
                return False
            if "type" in value and ("description" in value or "properties" in value):
                return True
            return False

        if "dimensions" in data and isinstance(data.get("dimensions"), dict):
            if not is_schema_dict(data.get("dimensions")):
                if "overall_pass" in data and is_schema_dict(data.get("overall_pass")):
                    pass
                else:
                    has_real_overall = False
                    for k in ["overall_pass", "overall_score", "overall_reason"]:
                        if k in data and not is_schema_dict(data.get(k)):
                            has_real_overall = True
                            break
                    if has_real_overall:
                        return data

        for k, v in data.items():
            if isinstance(v, str):
                v_lower = v.lower()
                if len(v) > 500 or "let's" in v_lower or "wait" in v_lower or "think>" in v_lower:
                    continue

            norm_key = normalize_key(k)
            if norm_key in key_fields:
                if is_schema_dict(v) and norm_key != "dimensions":
                    continue
                if norm_key in cleaned and is_schema_dict(cleaned.get(norm_key)) and not is_schema_dict(v):
                    cleaned[norm_key] = v
                else:
                    cleaned[norm_key] = v
            elif isinstance(v, (int, float)):
                cleaned[norm_key] = v
            elif isinstance(v, str) and len(v) <= 500:
                cleaned[norm_key] = v
            elif isinstance(v, (list, dict)):
                cleaned[norm_key] = v

        for nested_key in ["entry", "properties"]:
            if nested_key in cleaned and isinstance(cleaned[nested_key], dict):
                nested = self._extract_structured_data(cleaned[nested_key])
                for k, v in nested.items():
                    if k not in cleaned or k == "dimensions":
                        cleaned[k] = v

        return cleaned

    def _parse_evaluation_result(self, data: dict, dimension_weights: Optional[dict] = None) -> dict:
        """
        解析并标准化评估结果
        
        Args:
            data: 从Dify Agent返回的JSON数据
        
        Returns:
            标准化的评估结果
        """
        if data is None:
            data = {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}

        if not isinstance(data, dict):
            data = {}

        cleaned_data = self._extract_structured_data(data)

        # 标准化结果结构
        result = {
            "pass": self._normalize_boolean(cleaned_data.get("overall_pass", True)),
            "overall_score": self._normalize_score(cleaned_data.get("overall_score", 0)),
            "overall_reason": str(cleaned_data.get("overall_reason", "")),
            "dimensions": {},
            "suggestions": cleaned_data.get("suggestions", [])
        }

        if isinstance(result["suggestions"], str):
            result["suggestions"] = [result["suggestions"]]
        elif not isinstance(result["suggestions"], list):
            result["suggestions"] = []
        
        # 解析各维度评分
        dimensions_data = cleaned_data.get("dimensions", {})
        if isinstance(dimensions_data, dict):
            for dim_name, dim_data in dimensions_data.items():
                if isinstance(dim_data, dict):
                    result["dimensions"][dim_name] = {
                        "score": self._normalize_score(dim_data.get("score", 0)),
                        "reason": str(dim_data.get("reason", "")),
                        "details": str(dim_data.get("details", ""))
                    }
                elif isinstance(dim_data, (int, float, str)):
                    # 兼容简化格式
                    result["dimensions"][dim_name] = {
                        "score": self._normalize_score(dim_data),
                        "reason": "",
                        "details": ""
                    }
        
        # 如果没有明确的overall_score，根据维度分数计算
        if result["overall_score"] == 0 and result["dimensions"]:
            # 使用传入的维度权重或默认权重计算综合分数
            weights = dimension_weights or {
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
