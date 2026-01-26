import re
import json

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class Evaluator:
    def __init__(self, judge_api_key=None, model="gpt-4o"):
        """
        初始化评估器
        :param judge_api_key: 可选。如果不传，则无法使用 soft_check，但可以使用 hard_check
        """
        self.client = None
        if judge_api_key and OpenAI:
            self.client = OpenAI(api_key=judge_api_key)

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
