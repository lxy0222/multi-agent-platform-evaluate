import random
import re
import logging

import requests
import json
import time

from src.client.base_cliet import BaseAgentClient


class DifyClient(BaseAgentClient):

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

    def send_message(self, query, inputs, user, response_mode="blocking", conversation_id="", compatible_mode=True, collect_tools=True):
        """
        发送对话
        :param query:
        :param inputs:
        :param user:
        :param response_mode:
        :param conversation_id:
        :param compatible_mode: True = 模拟 Java 客户端行为 (把当前 query 包装成 JSON 字符串发给 Dify)
                                False = 标准 Dify 行为 (query 传纯文本)
        :param collect_tools: True = 收集工具调用信息（默认，用于硬校验）
                              False = 跳过工具解析，仅返回 answer（用于软校验/LLM 评分，避免浪费时间）
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
            "response_mode": "streaming", # 强制改为流式输出，方便捕获工具调用
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
            # 开启 stream=True
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout, stream=True)

            # 检查 HTTP 状态码
            if response.status_code != 200:
                return {
                    "status": "http_error",
                    "answer": f"HTTP {response.status_code}: {response.text}",
                    "raw_outputs": {}
                }
            # response.raise_for_status()

            # 解析流式响应
            full_answer = ""
            task_id = None
            ret_conversation_id = conversation_id
            tool_calls = []
            raw_events = []

            if collect_tools:
                # 用于 agent_log 去重：seen_agent_log_ids 防止同一条 entry_id 被处理两次
                # round_id_to_entry 用于 CALL 子层通过 parent_id 找到对应 ROUND 记录并补充完整入参/出参
                seen_agent_log_ids = set()
                round_id_to_entry = {}  # round entry_id -> tool_calls 列表中对应的 dict 引用
                # node_id -> 节点名称映射，供 agent_log 反查父 Agent 节点名
                node_id_to_title = {}
            
            for line in response.iter_lines():
                if line:
                    decoded_string = line.decode('utf-8').strip()
                    if decoded_string.startswith('data:'):
                        data_str = decoded_string[5:].strip()
                        if not data_str or data_str == "ping":
                            continue
                        try:
                            event_data = json.loads(data_str)
                            raw_events.append(event_data)
                            event_type = event_data.get('event')

                            if event_type in ['message', 'agent_message']:
                                full_answer += event_data.get('answer', '')
                                if 'task_id' in event_data: task_id = event_data['task_id']
                                if 'conversation_id' in event_data: ret_conversation_id = event_data['conversation_id']
                            elif collect_tools and event_type == 'agent_thought':
                                tool_name = event_data.get('tool')
                                if tool_name:
                                    tool_calls.append({
                                        'tool': tool_name,
                                        'tool_input': event_data.get('tool_input'),
                                        'observation': event_data.get('observation')
                                    })
                            elif collect_tools and event_type in ['node_started', 'node_finished']:
                                # 收集 node_id -> title 映射，供 agent_log 反查调用节点名称
                                data_node = event_data.get('data', {})
                                _nid = data_node.get('node_id')
                                _ntitle = data_node.get('title')
                                if _nid and _ntitle:
                                    node_id_to_title[_nid] = _ntitle

                                if event_type == 'node_finished':
                                    # 兼容 Chatflow 中出现的画布工具节点
                                    node_type = data_node.get('node_type')
                                    title = data_node.get('title')
                                    if node_type in ['tool', 'http-request']:
                                        tool_calls.append({
                                            'tool': title,
                                            'caller_node': title,
                                            'node_type': node_type,
                                            'inputs': data_node.get('inputs'),
                                            'outputs': data_node.get('outputs')
                                        })
                            elif collect_tools and event_type == 'agent_log':
                                # 兼容 Chatflow 内部 Agent 节点的工具调用记录
                                # Dify agent_log 层次结构：
                                #   ROUND 汇总层 (parent_id=None)：每轮一条，含 action_name + observation。
                                #                                  每轮对应一次工具调用或 Final Answer。
                                #   Thought 子层 (parent_id=ROUND_id)：LLM思考，含 action + action_input。
                                #   CALL 子层 (parent_id=ROUND_id)：工具执行结果，含 tool_name + tool_call_args + output。
                                #              tool_call_args 比 ROUND 的 action_input 更完整（可能多额外字段）。
                                # 用 entry_id (data.id) 去重，防止 start+success 两条被重复处理。
                                outer = event_data.get('data', {})
                                entry_id = outer.get('id')
                                entry_status = outer.get('status')
                                parent_id = outer.get('parent_id')
                                label = outer.get('label', '')
                                # outer.node_id 是父级 Agent 节点的 ID，反查其名称
                                agent_node_id = outer.get('node_id')
                                agent_node_title = node_id_to_title.get(agent_node_id, agent_node_id)

                                if entry_status != 'success' or entry_id in seen_agent_log_ids:
                                    pass  # 跳过 start 事件和已处理过的 id
                                else:
                                    seen_agent_log_ids.add(entry_id)
                                    log_data = outer.get('data', {})

                                    if parent_id is None:
                                        # --- ROUND 汇总层 ---
                                        action_name = log_data.get('action_name') or log_data.get('action') or log_data.get('tool_name')
                                        # 排除 Final Answer 和非法工具名
                                        if (action_name
                                                and isinstance(action_name, str)
                                                and action_name != 'Final Answer'
                                                and not action_name.strip().startswith('{')):
                                            entry = {
                                                'tool': action_name,
                                                'caller_node': agent_node_title, # 记录调用该工具的 Agent 节点名
                                                'node_type': 'agent_log_tool',
                                                'inputs': log_data.get('action_input'),
                                                'tool_call_args': None,
                                                'outputs': log_data.get('observation'),
                                                'thought': log_data.get('thought')
                                            }
                                            tool_calls.append(entry)
                                            round_id_to_entry[entry_id] = entry

                                    elif label.startswith('CALL ') and parent_id in round_id_to_entry:
                                        # --- CALL 子层 ---
                                        target_entry = round_id_to_entry[parent_id]
                                        target_entry['tool_call_args'] = log_data.get('tool_call_args')
                                        if log_data.get('output'):
                                            target_entry['outputs'] = log_data.get('output')
                        except json.JSONDecodeError:
                            pass

            self.logger.info(f"抓取到流事件数: {len(raw_events)}, 识别出工具调用: {len(tool_calls)}次")
            if collect_tools and tool_calls:
                self.logger.info(f"识别到的工具调用详情（共 {len(tool_calls)} 次）:")
                for i, tc in enumerate(tool_calls, 1):
                    self.logger.info(f"  [{i}] 工具: {tc.get('tool')}  调用节点: {tc.get('caller_node', '-')}  类型: {tc.get('node_type')}")
                    # 入参：优先展示更完整的 tool_call_args，如是画布工具节点就用 inputs
                    actual_inputs = tc.get('tool_call_args') or tc.get('inputs')
                    self.logger.info(f"    入参: {json.dumps(actual_inputs, ensure_ascii=False, default=str)}")
                    self.logger.info(f"    出参: {json.dumps(tc.get('outputs'), ensure_ascii=False, default=str)}")

            parsed_answer = full_answer
            try:
                if isinstance(full_answer, str) and (
                        full_answer.strip().startswith('{') or full_answer.strip().startswith('[')):
                    parsed_answer = json.loads(full_answer)
            except json.JSONDecodeError:
                pass

            if task_id or full_answer:
                return {
                    "status": "success",
                    "answer": full_answer,
                    "json_data": parsed_answer,
                    "task_id": task_id,
                    "conversation_id": ret_conversation_id,
                    "tool_calls": tool_calls,
                    "raw_outputs": raw_events  
                }
            else:
                return {
                    "status": "error",
                    "answer": f"Dify Error (Empty Events) or Unknown",
                    "raw_outputs": raw_events
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

    def run_workflow(self, inputs: dict, user: str, collect_tools: bool = True) -> dict:
        """
        调用 Dify Workflow 执行接口
        :param collect_tools: True = 收集工具调用信息（默认，用于硬校验）
                              False = 跳过工具解析，仅返回最终 outputs
        """
        url = f"{self.base_url}/workflows/run"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "inputs": inputs,
            "response_mode": "streaming", # 强制改为流式输出
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
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout, stream=True)
            
            # 记录响应信息
            self.logger.info(f"收到Dify Workflow响应 - 状态码: {response.status_code}")
            self.logger.info(f"响应耗时: {response.elapsed.total_seconds():.2f}秒")
            
            if response.status_code != 200:
                self.logger.error(f"Workflow请求失败: HTTP {response.status_code} - {response.text[:200]}")
                return {"status": "http_error", "answer": response.text}
            # response.raise_for_status()

            raw_events = []
            tool_calls = []
            workflow_run_id = None
            task_id = None
            outputs = {}
            status_val = "success"

            if collect_tools:
                # 用于 agent_log 去重
                seen_agent_log_ids = set()
                round_id_to_entry = {}  # round entry_id -> tool_calls 内对应 dict 的引用，用于 CALL 层补充入参/出参
                # node_id -> 节点名称映射，供 agent_log 反查父 Agent 节点名
                node_id_to_title = {}

            for line in response.iter_lines():
                if line:
                    decoded_string = line.decode('utf-8').strip()
                    if decoded_string.startswith('data:'):
                        data_str = decoded_string[5:].strip()
                        if not data_str or data_str == "ping":
                            continue
                        try:
                            event_data = json.loads(data_str)
                            raw_events.append(event_data)
                            event_type = event_data.get('event')
                            data_node = event_data.get('data', {})

                            if collect_tools and event_type in ['node_started', 'node_finished']:
                                # 收集 node_id -> title 映射，供 agent_log 反查调用节点名称
                                _nid = data_node.get('node_id')
                                _ntitle = data_node.get('title')
                                if _nid and _ntitle:
                                    node_id_to_title[_nid] = _ntitle

                            if collect_tools and event_type == 'node_finished':
                                node_type = data_node.get('node_type')
                                title = data_node.get('title')
                                if node_type in ['tool', 'http-request']:
                                    tool_calls.append({
                                        'tool': title,
                                        'caller_node': title,
                                        'node_type': node_type,
                                        'inputs': data_node.get('inputs'),
                                        'outputs': data_node.get('outputs')
                                    })
                            elif event_type == 'workflow_finished':
                                workflow_run_id = event_data.get('workflow_run_id')
                                task_id = event_data.get('task_id')
                                outputs = data_node.get('outputs', {})
                                status_val = data_node.get('status', 'success')
                            elif collect_tools and event_type == 'agent_log':
                                # 兼容工作流里的 Agent 工具调用记录，与 send_message 相同策略
                                # data_node 即 event_data['data']
                                entry_id = data_node.get('id')
                                entry_status = data_node.get('status')
                                parent_id = data_node.get('parent_id')
                                label = data_node.get('label', '')
                                # 反查父级 Agent 节点名称
                                agent_node_id = data_node.get('node_id')
                                agent_node_title = node_id_to_title.get(agent_node_id, agent_node_id)

                                if entry_status != 'success' or entry_id in seen_agent_log_ids:
                                    pass  # 跳过 start 事件和已处理
                                else:
                                    seen_agent_log_ids.add(entry_id)
                                    log_data = data_node.get('data', {})

                                    if parent_id is None:
                                        # --- ROUND 汇总层 ---
                                        action_name = log_data.get('action_name') or log_data.get('action') or log_data.get('tool_name')
                                        if (action_name
                                                and isinstance(action_name, str)
                                                and action_name != 'Final Answer'
                                                and not action_name.strip().startswith('{')):
                                            entry = {
                                                'tool': action_name,
                                                'caller_node': agent_node_title,
                                                'node_type': 'agent_log_tool',
                                                'inputs': log_data.get('action_input'),
                                                'tool_call_args': None,
                                                'outputs': log_data.get('observation'),
                                                'thought': log_data.get('thought')
                                            }
                                            tool_calls.append(entry)
                                            round_id_to_entry[entry_id] = entry

                                    elif label.startswith('CALL ') and parent_id in round_id_to_entry:
                                        # --- CALL 子层：补充更完整的入参和出参 ---
                                        target_entry = round_id_to_entry[parent_id]
                                        target_entry['tool_call_args'] = log_data.get('tool_call_args')
                                        if log_data.get('output'):
                                            target_entry['outputs'] = log_data.get('output')
                        except json.JSONDecodeError:
                            pass

            self.logger.info(f"\u6293取到Workflow流事件数: {len(raw_events)}, 识别出工具调用/HTTP节点: {len(tool_calls)}次")
            if tool_calls:
                self.logger.info(f"识别到的工具调用详情（共 {len(tool_calls)} 次）:")
                for i, tc in enumerate(tool_calls, 1):
                    self.logger.info(f"  [{i}] 工具: {tc.get('tool')}  调用节点: {tc.get('caller_node', '-')}  类型: {tc.get('node_type')}")
                    actual_inputs = tc.get('tool_call_args') or tc.get('inputs')
                    self.logger.info(f"    入参: {json.dumps(actual_inputs, ensure_ascii=False, default=str)}")
                    self.logger.info(f"    出参: {json.dumps(tc.get('outputs'), ensure_ascii=False, default=str)}")

            output_content = outputs.get('output', '') if isinstance(outputs, dict) else str(outputs)
            parsed_data = self._safe_json_parse(output_content)

            return {
                "status": status_val,
                "answer": output_content, 
                "json_data": parsed_data,
                "workflow_run_id": workflow_run_id,
                "task_id": task_id,
                "tool_calls": tool_calls,
                "raw_outputs": raw_events
            }

        except Exception as e:
            return {"status": "error", "answer": str(e)}