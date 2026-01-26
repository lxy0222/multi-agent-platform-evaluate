from src.utils.dynamic_renderer import renderer
from src.utils.file_loader import load_excel_cases

try:
    test_cases = load_excel_cases("src/data/xiaofang_fz_todo.csv")
except FileNotFoundError:
    test_cases = load_excel_cases("data/xiaofang_fz_todo.csv")

repeat_count = 0

import pytest
import allure
import json
import csv
import os


# ==========================================
# 工具函数：加载 CSV 数据
# ==========================================
def load_csv_data(file_path):
    """
    读取CSV文件并返回为字典列表
    """
    data_list = []
    # 获取当前脚本所在目录的绝对路径，防止路径错误
    base_path = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_path, file_path)

    try:
        with open(full_path, mode='r', encoding='utf-8-sig') as f:  # utf-8-sig 解决Excel保存CSV带BOM的问题
            reader = csv.DictReader(f)
            for row in reader:
                data_list.append(row)
    except FileNotFoundError:
        print(f"❌ 未找到数据文件: {full_path}")
        return []

    return data_list


# 加载数据 (假设 csv 在同级目录下的 data 文件夹中)
# 如果你的文件在其他地方，请修改这里的路径
TEST_DATA = load_csv_data("data/fz_todo_cases.csv")


class TestFzToDo:

    # 使用 parametrize 实现参数化
    # case_data 会自动接收列表中的每一行字典
    @pytest.mark.parametrize("case_data", test_cases)
    def test_reply_with_thinking_case(self, case_data, client_factory, evaluator):

        # 动态更新 Allure 标题，方便在报告中区分不同用例
        allure.dynamic.title(f"复诊执行待办：{case_data.get('场景描述', '未命名用例')}")

        # ==========================================
        # 1. 构造 inputs
        # ==========================================
        with allure.step("步骤1: 构造请求数据"):

            raw_inputs_str = case_data.get('Dynamic_Inputs', '{}')
            raw_detail_str = case_data.get('Order_Detail', '')
            raw_messages_str = case_data.get('Chat_History', '')

            try:
                rendered_inputs = renderer.render(raw_inputs_str)
                inputs = json.loads(rendered_inputs)
            except json.JSONDecodeError as e:
                pytest.fail(f"CSV 中 orderDetail JSON 格式错误: {e}")

            # --- 处理 messages ---
            if raw_messages_str:
                try:
                    rendered_messages = renderer.render(raw_messages_str)

                    messages_obj = json.loads(rendered_messages)

                    inputs['messages'] = json.dumps(messages_obj, ensure_ascii=False)
                except json.JSONDecodeError:
                    pytest.fail(f"CSV 中 messages JSON 格式错误")

            if raw_detail_str:
                print("检测到 Order_Detail 列有值，正在合并...")
                try:
                    # 渲染 Order_Detail 里的动态变量
                    rendered_detail = renderer.render(raw_detail_str)

                    detail_obj = json.loads(rendered_detail)

                    inputs['orderDetail'] = json.dumps(detail_obj, ensure_ascii=False)

                except json.JSONDecodeError as e:
                    pytest.fail(f"CSV 中 Order_Detail JSON 格式错误: {e}")
                except Exception as e:
                    pytest.fail(f"Order_Detail 渲染失败: {e}")
            if raw_detail_str:
                print("检测到 Order_Detail 列有值，正在合并...")
                try:
                    # 渲染 Order_Detail 里的动态变量
                    rendered_detail = renderer.render(raw_detail_str)

                    detail_obj = json.loads(rendered_detail)

                    inputs['orderDetail'] = json.dumps(detail_obj, ensure_ascii=False)

                except json.JSONDecodeError as e:
                    pytest.fail(f"CSV 中 Order_Detail JSON 格式错误: {e}")
                except Exception as e:
                    pytest.fail(f"Order_Detail 渲染失败: {e}")

            # 附加到报告
            allure.attach(
                json.dumps(inputs, ensure_ascii=False, indent=4),
                name="完整请求参数 (Inputs+oderDetail)",
                attachment_type=allure.attachment_type.JSON
            )

        # ==========================================
        # 2. 执行 Workflow
        # ==========================================
        with allure.step("步骤2: 执行工作流接口"):
            print(f"正在执行: {case_data.get('场景描述')}")
            client = client_factory("todo_exec_follow")
            response = client.run_workflow(inputs, user="18816")

            allure.attach(
                json.dumps(response, ensure_ascii=False, indent=4),
                name="接口响应结果 (Response)",
                attachment_type=allure.attachment_type.JSON
            )

        # ==========================================
        # 3. 执行校验
        # ==========================================
        with allure.step("步骤3: 结果校验与断言"):
            if response["status"] != "succeeded":
                pytest.fail(f"失败: 工作流执行状态异常，ID: {response.get('workflow_run_id')}")

            ai_answer = response.get("answer", "")
            allure.attach(ai_answer, name="AI最终回复内容", attachment_type=allure.attachment_type.TEXT)

            # 从 CSV 获取预期的校验点 (默认为 Reply)
            check_point = case_data.get('expected_check_point', 'Reply')

            # 调用评估器
            passed, errors = evaluator.hard_check(ai_answer, check_point)

            if not passed:
                allure.attach(
                    json.dumps(errors, ensure_ascii=False, indent=4),
                    name="断言失败详情",
                    attachment_type=allure.attachment_type.JSON
                )
                pytest.fail(f"校验失败: {errors}")
            else:
                allure.attach("所有校验规则均通过", name="校验通过验结果", attachment_type=allure.attachment_type.TEXT)



# class TestFzToDo:
#
#     @pytest.mark.repeat(repeat_count)
#     @allure.title("复诊执行待办工作流：回复包含思考过程测试")
#     @allure.description("测试验证AI回复是否符合预期不包含思考过程")
#     def test_reply_with_thinking_case(self, client_factory, evaluator):
#         # ==========================================
#         # 1. 构造 inputs (放入 step 中更清晰)
#         # ==========================================
#         with allure.step("步骤1: 构造请求数据"):
#
#             orderDetail = {
#                 "text": "",
#                 "files": [],
#                 "json": [
#                     {
#                         "方案病症": "脂肪瘤·气滞痰凝证",
#                         "剂型": "免煎颗粒",
#                         "收货人": "孙先生",
#                         "患者姓名": "孙俊杰",
#                         "每日几帖": 1,
#                         "预计服用天数": 6,
#                         "预计复诊时间": "2025-11-27 17:49:51",
#                         "发货时间": "2025-11-20 16:14:31",
#                         "收货时间": "2025-11-21 17:49:51",
#                         "帖数": 6,
#                         "订单编号": "DJO000791365456225",
#                         "专病名称": "非专病",
#                         "一帖分几次服用": 2,
#                         "医嘱": "无",
#                         "订单状态": "已签收",
#                         "收货地址": "内蒙古自治区呼和浩特市赛罕区泽信·青城一期一号楼一单元1201如意和大街呼和浩特海关东侧",
#                         "药品详情": "川芎2.1克；当归4.2克；生白芍4.2克；防风4.2克；木香4.2克；生黄芪4.2克；肉桂4.2克；桔梗4.2克；白芷4.2克；厚朴4.2克；乌药4.2克；甘草4.2克；紫苏叶4.2克；枳壳4.2克；党参4.2克；焦槟榔4.2克；"
#                     }
#                 ]
#             }
#             orderDetailStr = json.dumps(orderDetail, ensure_ascii=False)
#
#             inputs = {
#                 "patientId": 4008271,
#                 "orderCode": "DJO000791365456225",
#                 "scene": "37",
#                 "medicinePurchaseCnt": 2,
#                 "followUpCareCnt": 2,
#                 "isFollowUpVisit": 1,
#                 "messages": "[]",  # 这里你使用的是空字符串，确认是否符合预期
#                 "orderDetail": orderDetailStr
#             }
#
#             # 【关键点1】将 inputs 附加到报告中
#             allure.attach(
#                 json.dumps(inputs, ensure_ascii=False, indent=4),
#                 name="完整请求参数 (Inputs)",
#                 attachment_type=allure.attachment_type.JSON
#             )
#
#         # ==========================================
#         # 2. 执行 Workflow
#         # ==========================================
#         with allure.step("步骤2: 执行工作流接口"):
#             print(f"正在执行回放测试")
#             client = client_factory("todo_exec_follow")
#             response = client.run_workflow(inputs, user="18816")
#
#             # 【关键点2】将 Response 附加到报告中
#             # 无论成功失败，都能看到返回了什么，非常有助于调试
#             allure.attach(
#                 json.dumps(response, ensure_ascii=False, indent=4),
#                 name="接口响应结果 (Response)",
#                 attachment_type=allure.attachment_type.JSON
#             )
#
#         # ==========================================
#         # 3. 执行校验
#         # ==========================================
#         with allure.step("步骤3: 结果校验与断言"):
#             # 检查接口状态
#             if response["status"] != "succeeded":
#                 # 如果状态不对，直接报错并附带 ID
#                 pytest.fail(f"失败: 工作流执行状态异常，ID: {response.get('workflow_run_id', 'Unknown')}")
#
#             # 提取 AI 的回答
#             ai_answer = response.get("answer", "")
#             allure.attach(ai_answer, name="AI最终回复内容", attachment_type=allure.attachment_type.TEXT)
#
#             # 调用评估器
#             passed, errors = evaluator.hard_check(ai_answer, "Reply")
#
#             # 【关键点3】将校验过程/错误详情附加到报告
#             if not passed:
#                 allure.attach(
#                     json.dumps(errors, ensure_ascii=False, indent=4),
#                     name="断言失败详情 (Errors)",
#                     attachment_type=allure.attachment_type.JSON
#                 )
#                 pytest.fail(f"校验失败: {errors}")
#             else:
#                 # 即使通过了，也可以附加上去表示“校验通过”
#                 allure.attach("所有校验规则均通过", name="校验通过验结果", attachment_type=allure.attachment_type.TEXT)

#     @pytest.mark.repeat(repeat_count)
#     @allure.title("复诊执行待办工作流：回复包含英文测试")
#     @allure.description("测试验证AI回复是否符合预期英文含量低于80%")
#     def test_reply_with_English_case(self, client_factory, evaluator):
#         # ==========================================
#         # 1. 构造 inputs (放入 step 中更清晰)
#         # ==========================================
#         with allure.step("步骤1: 构造请求数据"):
#             chat_history_list = [{"role":"assistant","content":[{"type":"text","text":"我看你药已收到了，请按时吃药呀~按要求需饭后一小时服（早9:00、下午3:00）,忌生冷油腻辛辣"}],"time":"2025-12-18 11:05:23"},{"role":"assistant","content":[{"type":"text","text":"我看你药已收到，记得按时吃。饭后一小时服，早9:00、下午3:00，服药忌生冷、油腻、辛辣。"}],"time":"2025-12-18 13:25:13"},{"role":"user","content":[{"type":"text","text":"在吗"}],"time":"2025-12-26 11:21:39"},{"role":"assistant","content":[{"type":"text","text":"在的呀，有什么可以帮到你吗"}],"time":"2025-12-26 11:21:55"},{"role":"user","content":[{"type":"text","text":"查医生说送我一罐玫瑰花茶"}],"time":"2025-12-26 11:22:01"},{"role":"user","content":[{"type":"text","text":"来找你哈"}],"time":"2025-12-26 11:22:06"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你查一下订单信息"}],"time":"2025-12-26 11:22:26"},{"role":"user","content":[{"type":"text","text":"好的"}],"time":"2025-12-26 11:23:30"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你查一下订单信息"}],"time":"2025-12-26 11:23:45"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯 帮你安排了"}],"time":"2025-12-26 11:45:51"},{"role":"assistant","content":[{"type":"text","text":"估计需要2-3天送达"}],"time":"2025-12-26 11:46:06"},{"role":"user","content":[{"type":"text","text":"嗯嗯，好的"}],"time":"2025-12-26 12:05:29"},{"role":"assistant","content":[{"type":"text","text":"不客气，收到后记得查收"}],"time":"2025-12-26 12:05:45"},{"role":"user","content":[{"type":"text","text":"在吗"}],"time":"2025-12-29 11:20:38"},{"role":"user","content":[{"type":"text","text":"这次的快递怎么是天津发出的呢"}],"time":"2025-12-29 11:20:51"},{"role":"user","content":[{"type":"text","text":"今天是收不到了"}],"time":"2025-12-29 11:20:56"},{"role":"assistant","content":[{"type":"text","text":"在的呀，有什么可以帮到你吗"}],"time":"2025-12-29 11:20:59"},{"role":"user","content":[{"type":"text","text":"之前不是广东与杭州吗"}],"time":"2025-12-29 11:21:06"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你核实一下快递信息"}],"time":"2025-12-29 11:21:21"},{"role":"user","content":[{"type":"text","text":"回答下哈"}],"time":"2025-12-29 11:21:26"},{"role":"assistant","content":[{"type":"text","text":"不同仓库发货地会有差异呢"}],"time":"2025-12-29 11:21:31"},{"role":"assistant","content":[{"type":"text","text":"我们会尽快为你安排配送的"}],"time":"2025-12-29 11:21:42"},{"role":"user","content":[{"type":"text","text":"之前都是杭州发出"}],"time":"2025-12-29 11:21:45"},{"role":"assistant","content":[{"type":"text","text":"不同仓库发货地会有差异呢"}],"time":"2025-12-29 11:21:53"},{"role":"user","content":[{"type":"text","text":"这次怎么那么远"}],"time":"2025-12-29 11:21:58"},{"role":"assistant","content":[{"type":"text","text":"不同仓库发货地会有差异呢"}],"time":"2025-12-29 11:22:05"},{"role":"user","content":[{"type":"text","text":"下次帮我就近仓库发出哈"}],"time":"2025-12-29 11:22:11"},{"role":"assistant","content":[{"type":"text","text":"我们会尽快为你安排配送的"}],"time":"2025-12-29 11:22:16"},{"role":"assistant","content":[{"type":"text","text":"不同订单会根据库存情况从最近的仓库发出"}],"time":"2025-12-29 11:22:26"},{"role":"assistant","content":[{"type":"text","text":"我们会尽量加快配送速度的"}],"time":"2025-12-29 11:22:37"},{"role":"user","content":[{"type":"text","text":"太远影响收货影响服药时间了"}],"time":"2025-12-29 11:22:44"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯 记下你的需求啦"}],"time":"2025-12-29 11:22:49"},{"role":"assistant","content":[{"type":"text","text":"后续会尽量为你安排就近仓库发货"}],"time":"2025-12-29 11:22:59"},{"role":"user","content":[{"type":"text","text":"发货地不要改来改去哈"}],"time":"2025-12-29 11:23:07"},{"role":"assistant","content":[{"type":"text","text":"理解你的担心呢"}],"time":"2025-12-29 11:23:10"},{"role":"assistant","content":[{"type":"text","text":"我们会催促快递尽快送达的"}],"time":"2025-12-29 11:23:20"},{"role":"user","content":[{"type":"text","text":"我以为今天能收到"}],"time":"2025-12-29 11:23:21"},{"role":"assistant","content":[{"type":"text","text":"我们会尽量固定发货仓库的"}],"time":"2025-12-29 11:23:29"},{"role":"user","content":[{"type":"text","text":"再催今天也到不了"}],"time":"2025-12-29 11:23:36"},{"role":"assistant","content":[{"type":"text","text":"后续会优先安排就近仓库为你发货"}],"time":"2025-12-29 11:23:40"},{"role":"user","content":[{"type":"text","text":"发货地那么远"}],"time":"2025-12-29 11:23:42"},{"role":"assistant","content":[{"type":"text","text":"我们会再和快递确认下进度的"}],"time":"2025-12-29 11:23:52"},{"role":"user","content":[{"type":"text","text":"「大家中医医生助理小方：后续会优先安排就近仓库为你发货」n- - - - - - - - - - - - - - -n好"}],"time":"2025-12-29 11:23:52"},{"role":"assistant","content":[{"type":"text","text":"抱歉让你久等了"}],"time":"2025-12-29 11:24:03"},{"role":"assistant","content":[{"type":"text","text":"理解你的心情呢"}],"time":"2025-12-29 11:24:13"},{"role":"assistant","content":[{"type":"text","text":"我们会持续关注物流状态的"}],"time":"2025-12-29 11:24:24"},{"role":"assistant","content":[{"type":"text","text":"后续会优先安排就近仓库为你发货"}],"time":"2025-12-29 11:24:35"},{"role":"assistant","content":[{"type":"text","text":"我们会尽量固定发货仓库的"}],"time":"2025-12-29 11:24:46"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯 放心吧"}],"time":"2025-12-29 11:24:57"},{"role":"user","content":[{"type":"text","text":"「大家中医医生助理小方：我们会尽量固定发货仓库的」n- - - - - - - - - - - - - - -n好，这次这么远发过来，今天这药就吃不上了"}],"time":"2025-12-29 11:26:08"},{"role":"assistant","content":[{"type":"text","text":"理解你的着急呢"}],"time":"2025-12-29 11:26:26"},{"role":"assistant","content":[{"type":"text","text":"我们会再和快递确认下进度的"}],"time":"2025-12-29 11:26:33"},{"role":"user","content":[{"type":"text","text":"SF5106093730011"}],"time":"2025-12-29 17:14:21"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你查询一下这个快递单号的物流信息"}],"time":"2025-12-29 17:14:38"},{"role":"user","content":[{"type":"text","text":"这个是今天刚抓的药，也是天津吗"}],"time":"2025-12-29 17:14:42"},{"role":"user","content":[{"type":"text","text":"也要等两天吗"}],"time":"2025-12-29 17:15:00"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你核实一下订单的发货信息"}],"time":"2025-12-29 17:15:01"},{"role":"assistant","content":[{"type":"text","text":"不同仓库发货地会有差异呢"}],"time":"2025-12-29 17:15:15"},{"role":"assistant","content":[{"type":"text","text":"我们会尽快为你安排配送的"}],"time":"2025-12-29 17:15:22"},{"role":"user","content":[{"type":"text","text":"为什么不杭州或者广东发货呢"}],"time":"2025-12-29 17:15:54"},{"role":"user","content":[{"type":"text","text":"第二天就可以收到"}],"time":"2025-12-29 17:16:04"},{"role":"assistant","content":[{"type":"text","text":"不同订单会根据库存情况从最近的仓库发出"}],"time":"2025-12-29 17:16:15"},{"role":"assistant","content":[{"type":"text","text":"我们会尽量固定发货仓库的"}],"time":"2025-12-29 17:16:21"},{"role":"assistant","content":[{"type":"text","text":"理解你希望尽快收到药品的心情呢"}],"time":"2025-12-29 17:16:28"},{"role":"assistant","content":[{"type":"text","text":"我们会催促仓库尽快发货并优先安排就近仓库"}],"time":"2025-12-29 17:16:34"},{"role":"assistant","content":[{"type":"text","text":"我昨天联系药房询问了下，是因为之前的药房有几味药材缺药了，所以给您换了一个药房"}],"time":"2025-12-30 10:45:09"},{"role":"user","content":[{"type":"text","text":"好的 ，刚才终于收到了谢谢"}],"time":"2025-12-30 10:46:04"},{"role":"assistant","content":[{"type":"text","text":"不客气，收到就好"}],"time":"2025-12-30 10:46:24"},{"role":"assistant","content":[{"type":"text","text":"药用着还习惯么？身体恢复得还好不？"}],"time":"2026-01-01 10:35:30"},{"role":"user","content":[{"type":"text","text":"还可以哈"}],"time":"2026-01-01 10:43:07"},{"role":"assistant","content":[{"type":"text","text":"那就好，继续坚持调理会越来越好的"}],"time":"2026-01-01 10:43:21"},{"role":"user","content":[{"type":"text","text":"嗯嗯"}],"time":"2026-01-01 10:43:32"},{"role":"assistant","content":[{"type":"text","text":"保持好心情对恢复也很重要呢"}],"time":"2026-01-01 10:43:50"},{"role":"user","content":[{"type":"text","text":"年底都可以抓药吧，"}],"time":"2026-01-01 10:43:56"},{"role":"assistant","content":[{"type":"text","text":"可以的呢，我们全年都有安排抓药服务"}],"time":"2026-01-01 10:44:10"},{"role":"user","content":[{"type":"text","text":"有放假没"}],"time":"2026-01-01 10:44:10"},{"role":"assistant","content":[{"type":"text","text":"需要的话随时和我说"}],"time":"2026-01-01 10:44:17"},{"role":"user","content":[{"type":"text","text":"好的"}],"time":"2026-01-01 10:44:23"},{"role":"assistant","content":[{"type":"text","text":"我们全年无休的呢"}],"time":"2026-01-01 10:44:26"},{"role":"assistant","content":[{"type":"revoke","text":""}],"time":"2026-01-01 10:44:30"},{"role":"assistant","content":[{"type":"text","text":"随时可以来复诊抓药"}],"time":"2026-01-01 10:44:44"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯，安心调理就好"}],"time":"2026-01-01 10:44:52"},{"role":"user","content":[{"type":"text","text":"好的，如果有放假安排提前说下哈"}],"time":"2026-01-01 10:45:39"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯，有变动的话会提前通知你的"}],"time":"2026-01-01 10:45:58"},{"role":"user","content":[{"type":"text","text":"在吗？今天医生是不是忘了给我开药了[捂脸]"}],"time":"2026-01-02 17:44:19"},{"role":"user","content":[{"type":"text","text":"查医生今天开的药什么时候发出呀"}],"time":"2026-01-02 20:19:28"},{"role":"assistant","content":[{"type":"text","text":"最近药按时吃着吗，身体感觉有没有好转一些"}],"time":"2026-01-02 22:18:58"},{"role":"assistant","content":[{"type":"text","text":"最近身体感觉怎么样，恢复情况还好吗？"}],"time":"2026-01-02 22:19:20"},{"role":"assistant","content":[{"type":"text","text":"最近身体状况还好吗，有没有需要留意的地方？"}],"time":"2026-01-02 22:25:33"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你查一下今天的处方信息"}],"time":"2026-01-02 22:25:44"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你查询一下订单的发货信息"}],"time":"2026-01-02 22:28:32"},{"role":"user","content":[{"type":"text","text":"好的"}],"time":"2026-01-02 22:36:51"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯，查到后会马上告诉你的"}],"time":"2026-01-02 22:37:13"},{"role":"assistant","content":[{"type":"text","text":"今天复诊后没买药，是有什么想法吗？和我说说吧。"}],"time":"2026-01-03 13:50:21"},{"role":"user","content":[{"type":"text","text":"昨天医生抓药了呢，今天在路上"}],"time":"2026-01-03 13:57:48"},{"role":"assistant","content":[{"type":"text","text":"收到啦，那记得留意物流信息"}],"time":"2026-01-03 13:58:06"},{"role":"assistant","content":[{"type":"text","text":"收到药后按时服用哦"}],"time":"2026-01-03 13:58:12"},{"role":"user","content":[{"type":"text","text":"今天孩子要吃完了"}],"time":"2026-01-03 13:58:28"},{"role":"user","content":[{"type":"text","text":"下午没药了"}],"time":"2026-01-03 13:58:34"},{"role":"user","content":[{"type":"text","text":"昨天中午复诊的"}],"time":"2026-01-03 13:58:44"},{"role":"assistant","content":[{"type":"text","text":"孩子的药快吃完的话，可以考虑复诊看看恢复情况"}],"time":"2026-01-03 13:58:45"},{"role":"assistant","content":[{"type":"text","text":"别着急，我帮你再催一下物流看看能不能尽快送到"}],"time":"2026-01-03 13:58:52"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯，那记得等药到了及时给孩子服用"}],"time":"2026-01-03 13:59:00"},{"role":"user","content":[{"type":"text","text":"昨天下午就是给孩子复诊的"}],"time":"2026-01-03 13:59:02"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯，了解啦，那等药到了及时给孩子服用"}],"time":"2026-01-03 13:59:20"},{"role":"assistant","content":[{"type":"text","text":"后续有什么情况随时和我说"}],"time":"2026-01-03 13:59:25"},{"role":"assistant","content":[{"type":"text","text":"孩子现在身体情况还好吗，有好转吗？"}],"time":"2026-01-04 10:35:27"},{"role":"user","content":[{"type":"text","text":"孩子的药还没收到哦"}],"time":"2026-01-04 10:36:25"},{"role":"assistant","content":[{"type":"text","text":"稍等我帮你查一下物流信息"}],"time":"2026-01-04 10:36:50"},{"role":"user","content":[{"type":"text","text":"昨天早上吃完的"}],"time":"2026-01-04 10:37:01"},{"role":"assistant","content":[{"type":"text","text":"孩子的药昨天已经发出了"}],"time":"2026-01-04 10:37:29"},{"role":"assistant","content":[{"type":"text","text":"我再帮你催下物流尽快送到"}],"time":"2026-01-04 10:37:37"},{"role":"user","content":[{"type":"text","text":"快递员等下会派送了"}],"time":"2026-01-04 10:37:41"},{"role":"user","content":[{"type":"text","text":"已经打电话给我了"}],"time":"2026-01-04 10:37:49"},{"role":"assistant","content":[{"type":"text","text":"那就好，收到后记得按时给孩子服药"}],"time":"2026-01-04 10:37:58"},{"role":"assistant","content":[{"type":"text","text":"有任何问题随时和我说"}],"time":"2026-01-04 10:38:06"},{"role":"assistant","content":[{"type":"text","text":"那就好，收到后记得按时给孩子服用"}],"time":"2026-01-04 10:38:12"},{"role":"assistant","content":[{"type":"text","text":"后续有什么情况随时和我说"}],"time":"2026-01-04 10:38:19"},{"role":"user","content":[{"type":"text","text":"嗯嗯"}],"time":"2026-01-04 10:38:19"},{"role":"assistant","content":[{"type":"text","text":"那就好，安心给孩子用药吧"}],"time":"2026-01-04 10:38:38"}]
#
#             # 注意：如果 chat_history_list 需要传给 inputs，请在这里修改，目前你传的是 "[]"
#             history_json_str = json.dumps(chat_history_list, ensure_ascii=False)
#
            # orderDetail = {
            #               "text": "",
            #               "files": [],
            #               "json": [
            #                 {
            #                   "方案病症": "鼻炎调理",
            #                   "剂型": "免煎颗粒",
            #                   "收货人": "吴松芝",
            #                   "患者姓名": "贾景昊",
            #                   "每日几帖": 1,
            #                   "预计服用天数": 3,
            #                   "预计复诊时间": "2026-01-07 11:36:10",
            #                   "发货时间": "2026-01-03 08:59:57",
            #                   "收货时间": "2026-01-04 11:36:10",
            #                   "帖数": 3,
            #                   "订单编号": "DJO000791375780727",
            #                   "专病名称": "非专病",
            #                   "一帖分几次服用": 2,
            #                   "医嘱": "饮食须知：忌甜、辣、酒、茶、咖啡。其中，甜，除了糖、巧克力、蛋糕、水果外，还包括牛奶、酸奶、坚果、糯米等食物。茶，包括红茶、绿茶、普洱等一切茶叶，但不包括菊花、玫瑰等花类代茶饮。",
            #                   "订单状态": "已签收",
            #                   "收货地址": "浙江省温州市龙湾区远洋·天铂华庭1幢2单元2206星海街道滨海十九路417号",
            #                   "药品详情": "桂枝4.2克；黄芩4.2克；生白芍4.2克；炙甘草2.1克；姜半夏4.2克；大枣4.2克；生姜4.2克；柴胡4.2克；太子参6.3克；紫苏梗4.2克；麸炒白术4.2克；茯苓6.3克；蜜麻黄1.0克；"
            #                 }
            #               ]
            #             }
#             orderDetailStr = json.dumps(orderDetail, ensure_ascii=False)
#
            # inputs = {
            #     "patientId": 4021153,
            #     "orderCode": "DJO000791375780727",
            #     "scene": "10",
            #     "medicinePurchaseCnt": 5,
            #     "followUpCareCnt": 5,
            #     "isFollowUpVisit": 0,
            #     "messages": history_json_str,
            #     "orderDetail": orderDetailStr
            # }
#
#             allure.attach(
#                 json.dumps(inputs, ensure_ascii=False, indent=4),
#                 name="完整请求参数 (Inputs)",
#                 attachment_type=allure.attachment_type.JSON
#             )
#
#         # ==========================================
#         # 2. 执行 Workflow
#         # ==========================================
#         with allure.step("步骤2: 执行工作流接口"):
#             print(f"正在执行回放测试")
#             client = client_factory("todo_exec_follow")
#             response = client.run_workflow(inputs, user="4021153")
#
#             # 【关键点2】将 Response 附加到报告中
#             # 无论成功失败，都能看到返回了什么，非常有助于调试
#             allure.attach(
#                 json.dumps(response, ensure_ascii=False, indent=4),
#                 name="接口响应结果 (Response)",
#                 attachment_type=allure.attachment_type.JSON
#             )
#
#         # ==========================================
#         # 3. 执行校验
#         # ==========================================
#         with allure.step("步骤3: 结果校验与断言"):
#             # 检查接口状态
#             if response["status"] != "succeeded":
#                 # 如果状态不对，直接报错并附带 ID
#                 pytest.fail(f"失败: 工作流执行状态异常，ID: {response.get('workflow_run_id', 'Unknown')}")
#
#             # 提取 AI 的回答
#             ai_answer = response.get("answer", "")
#             allure.attach(ai_answer, name="AI最终回复内容", attachment_type=allure.attachment_type.TEXT)
#
#             # 调用评估器
#             passed, errors = evaluator.hard_check(ai_answer, "Reply")
#
#             # 【关键点3】将校验过程/错误详情附加到报告
#             if not passed:
#                 allure.attach(
#                     json.dumps(errors, ensure_ascii=False, indent=4),
#                     name="断言失败详情 (Errors)",
#                     attachment_type=allure.attachment_type.JSON
#                 )
#                 pytest.fail(f"校验失败: {errors}")
#             else:
#                 # 即使通过了，也可以附加上去表示“校验通过”
#                 allure.attach("所有校验规则均通过", name="校验结果", attachment_type=allure.attachment_type.TEXT)
#
#     @pytest.mark.repeat(repeat_count)
#     @allure.title("复诊执行待办工作流：回复包含日文和emoji测试")
#     @allure.description("测试验证AI回复是否符合预期不能输出日文")
#     def test_reply_with_Japanese_and_emoji_case(self, client_factory, evaluator):
#         # ==========================================
#         # 1. 构造 inputs (放入 step 中更清晰)
#         # ==========================================
#         with allure.step("步骤1: 构造请求数据"):
#             chat_history_list = [{"role":"user","content":[{"type":"text","text":"我已经添加了你，现在我们可以开始聊天了。"}],"time":"2026-01-03 13:42:57"},{"role":"assistant","content":[{"type":"text","text":"您好，后续药到了我会提醒您具体服用方式的哈，日常有什么问题也可以和我说"}],"time":"2026-01-03 13:43:12"},{"role":"user","content":[{"type":"text","text":"[OK]"}],"time":"2026-01-03 13:45:32"},{"role":"assistant","content":[{"type":"text","text":"嗯嗯，有需要随时叫我"}],"time":"2026-01-03 13:45:50"}]
#
#             # 注意：如果 chat_history_list 需要传给 inputs，请在这里修改，目前你传的是 "[]"
#             history_json_str = json.dumps(chat_history_list, ensure_ascii=False)
#
            # orderDetail = {
            #               "text": "",
            #               "files": [],
            #               "json": [
            #                 {
            #                   "方案病症": "调理·阴血不足证",
            #                   "剂型": "免煎颗粒",
            #                   "收货人": "周丽",
            #                   "患者姓名": "周丽",
            #                   "每日几帖": 1,
            #                   "预计服用天数": 7,
            #                   "预计复诊时间": "2026-01-11 16:42:02",
            #                   "发货时间": "2026-01-03 17:52:38",
            #                   "收货时间": "2026-01-04 16:42:02",
            #                   "帖数": 7,
            #                   "订单编号": "DJO000791375943951",
            #                   "专病名称": "痤疮",
            #                   "一帖分几次服用": 2,
            #                   "医嘱": "无",
            #                   "订单状态": "已签收",
            #                   "收货地址": "湖南省长沙市岳麓区岳龙社区十片小区4单元308岳麓街道银杉路31号",
            #                   "药品详情": "熟地黄12.0克；山茱萸6.0克；生山药6.0克；牡丹皮3.0克；茯苓3.0克；泽泻3.0克；知母1.5克；枸杞子4.5克；菊花3.0克；桑叶3.0克；"
            #                 }
            #               ]
            #             }
#             orderDetailStr = json.dumps(orderDetail, ensure_ascii=False)
#
            # inputs = {
            #     "patientId": 4021153,
            #     "orderCode": "DJO000791375780727",
            #     "scene": "10",
            #     "medicinePurchaseCnt": 5,
            #     "followUpCareCnt": 5,
            #     "isFollowUpVisit": 0,
            #     "messages": history_json_str,
            #     "orderDetail": orderDetailStr
            # }
#
#             allure.attach(
#                 json.dumps(inputs, ensure_ascii=False, indent=4),
#                 name="完整请求参数 (Inputs)",
#                 attachment_type=allure.attachment_type.JSON
#             )
#
#         # ==========================================
#         # 2. 执行 Workflow
#         # ==========================================
#         with allure.step("步骤2: 执行工作流接口"):
#             print(f"正在执行回放测试")
#             client = client_factory("todo_exec_follow")
#             response = client.run_workflow(inputs, user="4021153")
#
#             # 【关键点2】将 Response 附加到报告中
#             # 无论成功失败，都能看到返回了什么，非常有助于调试
#             allure.attach(
#                 json.dumps(response, ensure_ascii=False, indent=4),
#                 name="接口响应结果 (Response)",
#                 attachment_type=allure.attachment_type.JSON
#             )
#
#         # ==========================================
#         # 3. 执行校验
#         # ==========================================
#         with allure.step("步骤3: 结果校验与断言"):
#             # 检查接口状态
#             if response["status"] != "succeeded":
#                 # 如果状态不对，直接报错并附带 ID
#                 pytest.fail(f"失败: 工作流执行状态异常，ID: {response.get('workflow_run_id', 'Unknown')}")
#
#             # 提取 AI 的回答
#             ai_answer = response.get("answer", "")
#             allure.attach(ai_answer, name="AI最终回复内容", attachment_type=allure.attachment_type.TEXT)
#
#             # 调用评估器
#             passed, errors = evaluator.hard_check(ai_answer, "Reply")
#
#             # 【关键点3】将校验过程/错误详情附加到报告
#             if not passed:
#                 allure.attach(
#                     json.dumps(errors, ensure_ascii=False, indent=4),
#                     name="断言失败详情 (Errors)",
#                     attachment_type=allure.attachment_type.JSON
#                 )
#                 pytest.fail(f"校验失败: {errors}")
#             else:
#                 # 即使通过了，也可以附加上去表示“校验通过”
#                 allure.attach("所有校验规则均通过", name="校验结果", attachment_type=allure.attachment_type.TEXT)
#
#
#     time.sleep(3)