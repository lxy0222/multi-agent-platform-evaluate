"""
统一的测试脚本
支持所有类型的测试用例，支持选择性执行
"""
import time
import pytest
import allure
import json
from src.utils.case_loader import CaseLoader
from src.utils.test_executor import TestExecutor


# ==========================================
# 配置区：修改这里来选择要执行的测试
# ==========================================
# 要加载的测试文件列表
TEST_FILES = [
    # "xiaofang_fz_chat.csv",
    "xiaofang_fz_todo.csv",  # 取消注释以启用
]

# 过滤条件（可选）
CASE_FILTER = {
    # "case_ids": ["CASE_01", "CASE_02"],  # 只执行指定用例
    # "target_agents": ["follow_up"],  # 只执行指定智能体
    # "tags": ["Reply"],  # 包含指定标签
    # "enabled": True,  # 只执行启用的用例
}

# 全局会话缓存
HISTORY_CACHE = {}


# ==========================================
# 加载测试用例
# ==========================================
def load_test_cases():
    """加载测试用例"""
    loader = CaseLoader(data_dir="data")

    # 加载用例
    try:
        # 检查CASE_FILTER是否有实际的过滤条件
        has_filter = any(v for v in CASE_FILTER.values() if v)
        filter_to_use = CASE_FILTER if has_filter else None

        cases = loader.load_multiple_files(TEST_FILES, case_filter=filter_to_use)
        print(f"\n✅ 成功加载 {len(cases)} 条测试用例")

        if filter_to_use:
            print(f"   应用的过滤条件: {filter_to_use}")
    except Exception as e:
        print(f"❌ 加载测试用例失败: {e}")
        import traceback
        traceback.print_exc()
        cases = []

    if not cases:
        print("⚠️ 没有找到任何测试用例")

    return cases


# 加载用例
test_cases = load_test_cases()


# ==========================================
# 测试类
# ==========================================
@allure.epic("统一测试框架")
@allure.feature("多智能体回归测试")
class TestUnifiedFramework:
    """统一测试框架"""
    
    @pytest.mark.parametrize("case", test_cases, ids=lambda c: c.case_id)
    def test_unified_case(self, case, client_factory, evaluator):
        """
        统一的测试用例执行方法
        
        Args:
            case: UnifiedTestCase 实例
            client_factory: 客户端工厂 fixture
            evaluator: 评估器 fixture
        """
        # 设置动态标题
        allure.dynamic.title(
            f"[{case.target_agent}] {case.case_id}: {case.scene_description}"
        )
        
        # 添加标签
        for tag in case.tags:
            allure.dynamic.tag(tag)
        
        # 添加优先级
        if case.priority >= 4:
            allure.dynamic.severity(allure.severity_level.CRITICAL)
        elif case.priority >= 3:
            allure.dynamic.severity(allure.severity_level.NORMAL)
        else:
            allure.dynamic.severity(allure.severity_level.MINOR)
        
        # 创建执行器
        executor = TestExecutor(client_factory, evaluator, HISTORY_CACHE)
        
        # ==========================================
        # 步骤1: 准备请求
        # ==========================================
        with allure.step("步骤1: 准备请求参数"):
            # 记录用例信息
            case_info = {
                "用例ID": case.case_id,
                "目标智能体": case.target_agent,
                "场景描述": case.scene_description,
                "用例类型": case.case_type.value,
                "预期动作": case.expected_action,
                "会话标识": case.session_key,
            }
            allure.attach(
                json.dumps(case_info, ensure_ascii=False, indent=2),
                name="用例信息",
                attachment_type=allure.attachment_type.JSON
            )
        
        # ==========================================
        # 步骤2: 执行测试
        # ==========================================
        with allure.step(f"步骤2: 执行测试 [{case.get_workflow_type().value}]"):
            result = executor.execute_case(case)
            
            # 记录请求参数
            allure.attach(
                json.dumps(result["request"], ensure_ascii=False, indent=2),
                name="请求参数",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 记录响应结果
            allure.attach(
                json.dumps(result["response"], ensure_ascii=False, indent=2),
                name="响应结果",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 提取AI回复
            ai_reply = executor._extract_reply(result["response"])
            allure.attach(
                ai_reply,
                name="AI回复内容",
                attachment_type=allure.attachment_type.TEXT
            )
        
        # ==========================================
        # 步骤3: 校验结果
        # ==========================================
        with allure.step("步骤3: 校验结果"):
            validation = result["validation"]
            
            # 记录校验详情
            allure.attach(
                json.dumps(validation, ensure_ascii=False, indent=2),
                name="校验详情",
                attachment_type=allure.attachment_type.JSON
            )
            
            # 断言
            if not result["success"]:
                error_msg = "\n".join(validation["errors"])
                allure.attach(
                    error_msg,
                    name="失败原因",
                    attachment_type=allure.attachment_type.TEXT
                )
                pytest.fail(f"测试失败:\n{error_msg}")
            else:
                allure.attach(
                    "✅ 所有校验通过",
                    name="校验结果",
                    attachment_type=allure.attachment_type.TEXT
                )
        
        # 缓冲时间（避免请求过快）
        time.sleep(2)

