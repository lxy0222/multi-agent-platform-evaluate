# tests/test_unified.py
import time
import pytest
import allure
import json
from utils.file_loader import load_excel_cases

try:
    # 加载包含所有智能体用例的大表
    test_cases = load_excel_cases("../data/golden_dataset.csv")
except FileNotFoundError:
    test_cases = load_excel_cases("data/golden_dataset.csv")

# =======================================================
# 全局字典：缓存 conversation_id
# =======================================================
HISTORY_CACHE = {}


@allure.epic("多智能体统一回归测试")
class TestXiaoFangFZAgents:

    # @pytest.mark.repeat(500)
    @pytest.mark.parametrize("case", test_cases)
    def test_dynamic_agent(self, case, client_factory, evaluator):

        agent_key = case['Target_Agent']
        case_id = case['Case_ID']
        session_key = case.get('Session_Key')

        # 1. 动态设置报告标题
        allure.dynamic.title(f"[{agent_key}] {case_id}: {case['场景描述']}")

        # 2. 从工厂获取对应的客户端
        try:
            client = client_factory(agent_key)
        except ValueError as e:
            pytest.fail(str(e))

        # 3. 解析差异化入参
        inputs = {}
        if case.get('Dynamic_Inputs'):
            try:
                raw_json = str(case['Dynamic_Inputs']).replace("'", '"')
                inputs = json.loads(raw_json)
            except json.JSONDecodeError:
                pytest.fail(f"Excel 中 Dynamic_Inputs 格式错误: {case['Dynamic_Inputs']}")

        user_query = case.get('Input_Query', '')

        # 4. 处理会话 ID
        current_conv_id = ""
        if session_key:
            if session_key in HISTORY_CACHE:
                current_conv_id = HISTORY_CACHE[session_key]
                print(f"🔄 [Context] 复用会话 {session_key}: {current_conv_id}")
            else:
                print(f"🆕 [Context] 开启新会话: {session_key}")

        # ==========================================
        # 核心步骤：调用智能体并记录请求/响应
        # ==========================================
        with allure.step(f"步骤1: 调用智能体 [{agent_key}]"):
            # A. 记录请求参数到报告
            request_payload = {
                "query": user_query,
                "inputs": inputs,
                "user": f"qa_{case_id}",
                "conversation_id": current_conv_id
            }
            allure.attach(
                json.dumps(request_payload, ensure_ascii=False, indent=4),
                name="完整请求参数 (Request)",
                attachment_type=allure.attachment_type.JSON
            )

            # B. 发起调用
            response = client.send_message(
                query=user_query,
                inputs=inputs,
                user=f"qa_{case_id}",
                conversation_id=current_conv_id
            )

            # C. 记录响应结果到报告
            allure.attach(
                json.dumps(response, ensure_ascii=False, indent=4),
                name="接口响应结果 (Response)",
                attachment_type=allure.attachment_type.JSON
            )

            # 提取数据用于后续处理
            structured_data = response.get('json_data')
            raw_text = response.get('answer', '')
            actual_conv_id = response.get('conversation_id')

        # 更新缓存
        if session_key and actual_conv_id:
            HISTORY_CACHE[session_key] = actual_conv_id

        # ==========================================
        # 校验步骤1：常规内容回复校验
        # ==========================================
        with allure.step("步骤2: 常规回复校验 (Hard Check)"):
            # 提取 AI 的实际回复文本
            real_reply = ""
            if isinstance(structured_data, dict):
                msg_list = structured_data.get("messageList", [])
                real_reply = msg_list[0].get("content", "") if msg_list else ""
            else:
                real_reply = raw_text

            # 将提取出的回复展示在报告中
            allure.attach(real_reply, name="AI 实际回复内容", attachment_type=allure.attachment_type.TEXT)
            allure.attach(str(case['Expected_Action']), name="预期回复关键点",
                          attachment_type=allure.attachment_type.TEXT)

            # 执行断言
            passed, errors = evaluator.hard_check(real_reply, case['Expected_Action'])

            if not passed:
                # 记录详细错误信息
                allure.attach(
                    json.dumps(errors, ensure_ascii=False, indent=4),
                    name="断言失败原因",
                    attachment_type=allure.attachment_type.JSON
                )
                pytest.fail(f"常规校验失败: {errors}")
            else:
                allure.attach("常规校验通过", name="校验结果", attachment_type=allure.attachment_type.TEXT)

        # ==========================================
        # 校验步骤2：特殊字段校验 (NeedHuman 等)
        # ==========================================
        # 只有当 Excel 的 Assert 列被标记（如标为 1 或 true）时才执行
        if case['Assert']:
            with allure.step("步骤3: 特殊字段校验 (转人工及空回复)"):
                # 1. 提取关键数据用于报告展示
                human_check_data = {
                    "needHuman": structured_data.get("needHuman"),
                    "humanReason": structured_data.get("humanReason"),
                    "messageList": structured_data.get("messageList", [])
                }
                allure.attach(
                    json.dumps(human_check_data, ensure_ascii=False, indent=4),
                    name="转人工相关字段数据",
                    attachment_type=allure.attachment_type.JSON
                )

                # 2. 校验 needHuman 是否为 True
                actual_need_human = structured_data.get("needHuman")
                assert actual_need_human is True, \
                    f"校验失败: 期望 needHuman 为 True，实际为 {actual_need_human} (原因: {response.get('humanReason')})"

                # 3. 校验 messageList 中所有的 content 是否都为空字符串
                msg_list = structured_data.get("messageList", [])

                if not msg_list:
                    allure.attach("messageList 为空列表", name="提示", attachment_type=allure.attachment_type.TEXT)

                for index, msg in enumerate(msg_list):
                    content = msg.get("content")
                    # 断言内容必须为空字符串 ""
                    assert content == "", \
                        f"校验失败: messageList 第 {index + 1} 条消息 content 不为空。实际内容: '{content}'"

                allure.attach("校验通过: 需人工处理且无自动回复内容", name="结果",
                              attachment_type=allure.attachment_type.TEXT)

        # 缓冲时间
        time.sleep(3)