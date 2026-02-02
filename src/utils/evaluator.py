import re
import json
from src.client.dify_client import DifyClient

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

    def hard_check(self, text, expected_type):
        """硬规则检查：不需要 API Key"""
        errors = []
        text = str(text)  # 确保输入是字符串

        # 1. 检查思维链
        if "<think>" in text or "</think>" in text:
            errors.append("包含思维链标签 <think>")

        # 2. 检查繁体字/英文 (示例)
        if len(re.findall(r'[a-zA-Z]{15,}', text)) > 0:
            errors.append("包含长英文句子")

        # 3. 预期动作检查
        if expected_type == "Block" and text.strip() != "":
            # 比如 text 为空才算 Block 成功
            # 或者 text 包含 "无需回复"
            pass

        if expected_type == "Delay" and "delay" not in text:
            # 如果不是完全等于 delay，可能需要报错
            pass

        return len(errors) == 0, errors

    def llm_evaluate(self, inputs, actual_output, scene, expected_output=None, context_inputs=None):
        """
        使用 Dify Agent 进行评估
        :param inputs: 用户当前的 query
        :param actual_output: AI 实际的回复
        :param scene: 场景描述
        :param expected_output: (新增) 预期的回复或动作，作为“标准答案”参考
        :param context_inputs: (新增) 对话的上下文变量，可能包含关键病历信息
        """
        if not self.dify_evaluator:
             return {
                "pass": True,
                "score": 0,
                "reason": "跳过：未配置 dify_evaluator，无法进行 LLM 评分"
            }
        
        # 构造发给 Dify 评估 Agent 的 Prompt
        # 加入了【上下文信息】和【标准参考答案】，让评估更准确
        prompt = f"""
        请作为专业的医疗客服质检员，对以下对话进行评估。

        ### 1. 测试背景
        - **场景**: {scene}
        - **上下文变量**: {json.dumps(context_inputs, ensure_ascii=False) if context_inputs else "无"}

        ### 2. 对话内容
        - **用户输入**: {inputs}
        - **AI实际回复**: {actual_output}

        ### 3. 评估标准参考
        - **预期行为/关键点 (Standard)**: {expected_output}

        ### 4. 你的任务
        请对比【AI实际回复】与【预期行为/关键点】：
        1. 准确性：是否包含了预期的关键信息？
        2. 依从性：是否执行了预期的动作（如转人工、开单等）？
        3. 亲切度：语气是否恰当？

        请输出 JSON 格式结果: {{"pass": true/false, "score": 0-100, "reason": "简短评价"}}
        """
        agent_inputs = {
            "user_query":inputs,
            "actual_output": actual_output,
            "scene_detail":scene,
            "expected_output":expected_output
        }
        
        try:
            # 调用 Dify Evaluator
            response = self.dify_evaluator.run_workflow(
                inputs=agent_inputs,
                user="evaluator_bot"
            )
            
            # 解析 Dify 的响应
            # 假设 Dify Evaluator 返回的是 JSON 格式的字符串
            result_text = response.get("answer", "")
            json_data = response.get("json_data")
            
            if json_data and isinstance(json_data, dict):
                 return json_data
            
            # 尝试从文本中解析 JSON
            # 有时候模型会包裹在 ```json ... ``` 中
            if result_text and "```json" in str(result_text):
                match = re.search(r"```json(.*?)```", str(result_text), re.DOTALL)
                if match:
                    json_str = match.group(1)
                    return json.loads(json_str)
            
            # 尝试直接解析
            try:
                if result_text:
                    return json.loads(str(result_text))
                return {"pass": False, "score": 0, "reason": "Evaluator returned empty response"}
            except:
                return {"pass": False, "score": 0, "reason": f"无法解析评估结果: {result_text}"}
                
        except Exception as e:
            return {"pass": False, "score": 0, "reason": f"评估过程发生错误: {str(e)}"}

    def soft_check(self, inputs, actual_output, scene):
        """LLM 裁判打分"""
        if not self.client:
            return {
                "pass": True,
                "score": 0,
                "reason": "跳过：未配置 judge.api_key，无法进行 LLM 评分"
            }
        prompt = f"""
        你是一个医疗客服质检员。
        场景: {scene}
        用户输入: {inputs}
        AI回复: {actual_output}

        请检查：
        1. 语气是否亲切？
        2. 是否符合医疗合规？
        3. 是否回答了用户问题？

        输出 JSON: {{"pass": true/false, "reason": "原因", "score": 0-10}}
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",  # 使用高智商模型做裁判
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            return {"pass": False, "reason": str(e), "score": 0}
