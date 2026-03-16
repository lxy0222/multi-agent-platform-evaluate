import random
import re
import logging

import requests
import json
import time

from src.client.base_cliet import BaseAgentClient


class DifyClient(BaseAgentClient):
    # def __init__(self, api_key: str, base_url: str):
    #     """
    #     初始化 Dify 客户端
    #     :param api_key: Dify 应用的 API Key (Secret Key)
    #     :param base_url: Dify API 地址，私有部署需替换为自己的域名
    #     """
    #     self.api_key = api_key
    #     self.base_url = base_url.rstrip('/')  # 去掉末尾可能多余的斜杠

    def __init__(self, config: dict):
        """
        初始化 Dify 客户端
        config 结构示例:
        {
            "api_key": "sk-...",
            "base_url": "https://api.dify.ai/v1",
            "compatible_mode": True,
            "timeout": 180  # 可选，默认 180 秒
        }
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        # 处理 base_url，去掉末尾斜杠
        raw_url = config.get("base_url", "undefined")
        self.base_url = raw_url.rstrip('/')

        # 将 compatible_mode 放入实例变量，也可在调用时覆盖
        self.default_compatible_mode = config.get("compatible_mode", True)
        
        # 超时配置（秒），默认 180 秒（3 分钟）
        self.timeout = config.get("timeout", 180)
        
        # 初始化日志记录器
        self.logger = logging.getLogger(f"client.{self.__class__.__name__}")
        if not self.logger.handlers:
            # 如果没有配置处理器，使用基础配置
            self.logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _generate_msg_id(self):
        """生成模拟的 msgId"""
        return f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}_external"

    def _parse_message_chain(self, raw_input: str) -> list:
        """
        核心解析逻辑：将带有 || 和 [TAG:...] 的字符串解析为标准 JSON 列表
        输入: "医生你好 || [IMAGE:http://xx.jpg]"
        输出: [{'msgType': 'text', 'content': '医生你好'...}, {'msgType': 'image', 'content': 'http://xx.jpg'...}]
        """
        payload_list = []

        # 1. 按 || 分割多条消息
        # 使用 filter 去除可能的空字符串
        segments = [s.strip() for s in str(raw_input).split('||') if s.strip()]

        for seg in segments:
            msg_data = {
                "msgId": self._generate_msg_id(),
                "msgType": "text",  # 默认为文本
                "content": seg
            }

            # 2. 识别图片标签 [IMAGE:url]
            img_match = re.match(r'^\[IMAGE:(.*?)\]$', seg, re.IGNORECASE)
            if img_match:
                msg_data["msgType"] = "image"
                msg_data["content"] = img_match.group(1).strip()  # 提取 URL

            # 3. 识别语音标签 [VOICE:url]
            voice_match = re.match(r'^\[VOICE:(.*?)\]$', seg, re.IGNORECASE)
            if voice_match:
                msg_data["msgType"] = "voice"
                msg_data["content"] = voice_match.group(1).strip()

            # 4. 识别视频或其他类型 (可扩展)
            # elif ...

            payload_list.append(msg_data)

        return payload_list

    def _safe_json_parse(self, content):
        """尝试将字符串解析为 JSON 对象/列表，失败返回原字符串"""
        if isinstance(content, str):
            content = content.strip()
            if content.startswith('{') or content.startswith('['):
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    pass
        return content

    def send_message(self, query, inputs, user, response_mode="blocking", conversation_id="",compatible_mode=True):
        """
        发送对话
        :param query:
        :param inputs:
        :param user:
        :param response_mode:
        :param conversation_id:
        :param compatible_mode: True = 模拟 Java 客户端行为 (把当前 query 包装成 JSON 字符串发给 Dify)
                                False = 标准 Dify 行为 (query 传纯文本)
        :return:
        """
        url = f"{self.base_url}/chat-messages"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if inputs is None:
            inputs = {}
        target_field = 'messages'  # Dify 变量名
        if target_field in inputs:
            raw_history = inputs[target_field]

            # 如果传入的是普通文本 (如 "医生你好||我头痛")，帮它转成 JSON 串
            # 如果传入的已经是 JSON 串 (如日志回放)，则保持不变
            is_json_str = isinstance(raw_history, str) and raw_history.strip().startswith('[')
            is_list_obj = isinstance(raw_history, list)

            if raw_history and not is_json_str and not is_list_obj:
                # 解析并序列化
                parsed_list = self._parse_message_chain(raw_history)
                inputs[target_field] = json.dumps(parsed_list, ensure_ascii=False)

            # 如果是 List 对象，转 JSON 串
            if is_list_obj:
                inputs[target_field] = json.dumps(raw_history, ensure_ascii=False)
        final_query = query
        if compatible_mode:
            # 如果 query 是纯文本，且没被包过
            is_query_json = isinstance(query, str) and query.strip().startswith('[')

            if query and not is_query_json:
                query_list = self._parse_message_chain(query)
                final_query = json.dumps(query_list, ensure_ascii=False)
        # 构造符合文档要求的 Body
        payload = {
            "inputs": inputs,
            "query": final_query,
            "response_mode": response_mode,
            "user": user,
            "auto_generate_name": False,
            "conversation_id": conversation_id
        }

        # 记录详细的请求信息
        try:
            self.logger.info(f"发送Dify请求 - 接口: {url}")
            self.logger.info(f"请求方法: POST")
            self.logger.info(f"请求头: Authorization=Bearer [API_KEY], Content-Type=application/json")
            self.logger.info(f"请求参数:")
            self.logger.info(f"  - response_mode: {response_mode}")
            self.logger.info(f"  - user: {user}")
            self.logger.info(f"  - conversation_id: {conversation_id}")
            self.logger.info(f"  - auto_generate_name: False")
            self.logger.info(f"  - compatible_mode: {compatible_mode}")
            
            # 记录query参数（敏感信息做脱敏处理）
            if final_query:
                if len(str(final_query)) > 500:
                    self.logger.info(f"  - query: {str(final_query)[:200]}...[{len(str(final_query))-200}字符已省略]")
                else:
                    self.logger.info(f"  - query: {final_query}")
            
            # 记录inputs参数（敏感信息做脱敏处理）
            if inputs:
                inputs_log = {}
                for key, value in inputs.items():
                    if isinstance(value, str) and len(value) > 200:
                        inputs_log[key] = f"{value[:100]}...[{len(value)-100}字符已省略]"
                    elif key in ['api_key', 'secret', 'password', 'token']:
                        inputs_log[key] = "[敏感信息已隐藏]"
                    else:
                        inputs_log[key] = value
                self.logger.info(f"  - inputs: {json.dumps(inputs_log, ensure_ascii=False)}")
            
            self.logger.info(f"超时设置: {self.timeout}秒")
        except Exception as log_e:
            self.logger.warning(f"记录请求日志时发生错误: {str(log_e)}")

        try:
            # 发起请求
            # timeout 使用配置的值，防止大模型生成太慢导致脚本挂起
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)

            # 检查 HTTP 状态码
            if response.status_code != 200:
                return {
                    "status": "http_error",
                    "answer": f"HTTP {response.status_code}: {response.text}",
                    "raw_outputs": {}
                }
            # response.raise_for_status()

            # 解析响应
            result = response.json()

            # 记录响应信息
            self.logger.info(f"收到Dify响应 - 状态码: {response.status_code}")
            self.logger.info(f"响应耗时: {response.elapsed.total_seconds():.2f}秒")
            self.logger.info(f"响应头: {dict(response.headers)}")
            
            # 记录响应体（敏感信息做脱敏处理）
            result_log = {}
            for key, value in result.items():
                if isinstance(value, str) and len(value) > 500:
                    result_log[key] = f"{value[:200]}...[{len(value)-200}字符已省略]"
                elif key in ['api_key', 'secret', 'password', 'token', 'bearer_token']:
                    result_log[key] = "[敏感信息已隐藏]"
                else:
                    result_log[key] = value
            self.logger.info(f"响应体: {json.dumps(result_log, ensure_ascii=False)}")

            # 【重要】标准化返回结果
            # Dify Workflow 的返回结构通常在 data.outputs 中
            # 即使 HTTP 200，Dify 内部也可能报错，需要检查
            if 'task_id' in result and 'answer' in result:
                raw_answer = result['answer']

                # 【关键步骤】尝试解析 JSON 字符串
                parsed_answer = raw_answer
                try:
                    if isinstance(raw_answer, str) and (
                            raw_answer.strip().startswith('{') or raw_answer.strip().startswith('[')):
                        parsed_answer = json.loads(raw_answer)
                except json.JSONDecodeError:
                    # 如果解析失败，说明是大模型直接输出的普通文本，不是 JSON
                    pass

                return {
                    "status": "success",
                    "answer": raw_answer,  # 原始字符串 (用于正则匹配/长度检查)
                    "json_data": parsed_answer,  # 解析后的对象 (用于字段检查)
                    "task_id": result.get('task_id'),
                    "conversation_id": result.get('conversation_id'),
                    "raw_outputs": result  # 保留完整元数据
                }
            else:
                return {
                    "status": "error",
                    "answer": f"Dify Error: {result}",
                    "raw_outputs": {}
                }

        except requests.exceptions.RequestException as e:
            # 网络层面的错误
            return {
                "status": "http_error",
                "answer": f"HTTP Request Failed: {str(e)}",
                "raw_outputs": {}
            }
        except Exception as e:
            # 其他未知错误
            return {
                "status": "exception",
                "answer": f"Unknown Error: {str(e)}",
                "raw_outputs": {}
            }

    def run_workflow(self, inputs: dict, user: str) -> dict:
        """
        调用 Dify Workflow 执行接口
        """
        url = f"{self.base_url}/workflows/run"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": user
        }

        # 记录详细的Workflow请求信息
        try:
            self.logger.info(f"发送Dify Workflow请求 - 接口: {url}")
            self.logger.info(f"请求方法: POST")
            self.logger.info(f"请求头: Authorization=Bearer [API_KEY], Content-Type=application/json")
            self.logger.info(f"请求参数:")
            self.logger.info(f"  - response_mode: blocking")
            self.logger.info(f"  - user: {user}")
            
            # 记录inputs参数（敏感信息做脱敏处理）
            if inputs:
                inputs_log = {}
                for key, value in inputs.items():
                    if isinstance(value, str) and len(value) > 200:
                        inputs_log[key] = f"{value[:100]}...[{len(value)-100}字符已省略]"
                    elif key in ['api_key', 'secret', 'password', 'token']:
                        inputs_log[key] = "[敏感信息已隐藏]"
                    else:
                        inputs_log[key] = value
                self.logger.info(f"  - inputs: {json.dumps(inputs_log, ensure_ascii=False)}")
            
            self.logger.info(f"超时设置: {self.timeout}秒")
        except Exception as log_e:
            self.logger.warning(f"记录Workflow请求日志时发生错误: {str(log_e)}")

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            
            # 记录响应信息
            self.logger.info(f"收到Dify Workflow响应 - 状态码: {response.status_code}")
            self.logger.info(f"响应耗时: {response.elapsed.total_seconds():.2f}秒")
            
            if response.status_code != 200:
                self.logger.error(f"Workflow请求失败: HTTP {response.status_code} - {response.text[:200]}")
                return {"status": "http_error", "answer": response.text}
            # response.raise_for_status()

            json_res = response.json()
            
            # 记录Workflow响应体
            try:
                response_log = {}
                for key, value in json_res.items():
                    if isinstance(value, (dict, list)):
                        if key == 'data' and isinstance(value, dict):
                            data_log = {}
                            for data_key, data_value in value.items():
                                if isinstance(data_value, str) and len(data_value) > 500:
                                    data_log[data_key] = f"{data_value[:200]}...[{len(data_value)-200}字符已省略]"
                                elif data_key in ['api_key', 'secret', 'password', 'token']:
                                    data_log[data_key] = "[敏感信息已隐藏]"
                                else:
                                    data_log[data_key] = data_value
                            response_log[key] = data_log
                        else:
                            response_log[key] = f"[{type(value).__name__}对象，长度: {len(str(value))}字符]"
                    elif isinstance(value, str) and len(value) > 500:
                        response_log[key] = f"{value[:200]}...[{len(value)-200}字符已省略]"
                    else:
                        response_log[key] = value
                
                self.logger.info(f"Workflow响应体: {json.dumps(response_log, ensure_ascii=False)}")
            except Exception as log_e:
                self.logger.warning(f"记录Workflow响应日志时发生错误: {str(log_e)}")
            
            data = json_res.get('data', {})

            output_content = data.get('outputs', {}).get('output', '')
            workflow_run_id = json_res.get('workflow_run_id')
            parsed_data = self._safe_json_parse(output_content)

            return {
                "status": data.get('status'),
                "answer": output_content,  # 提取出的最终内容
                "json_data": parsed_data,
                "workflow_run_id": workflow_run_id,
                "task_id": json_res.get('task_id'),
                "raw_outputs": data.get('outputs')  # 保留原始输出用于 Debug
            }

        except Exception as e:
            return {"status": "error", "answer": str(e)}