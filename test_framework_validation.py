#!/usr/bin/env python3
"""
框架验证脚本
用于验证重构后的框架是否正常工作
"""
import sys
import json
from src.utils.case_loader import CaseLoader
from src.utils.test_case_model import WorkflowType

def test_load_golden_dataset():
    """测试加载 xiaofang_fz_chat.csv"""
    print("\n" + "="*60)
    print("测试1: 加载 xiaofang_fz_chat.csv")
    print("="*60)
    
    loader = CaseLoader(data_dir="src/data")
    cases = loader.load_cases("xiaofang_fz_chat.csv")
    
    print(f"✅ 加载了 {len(cases)} 条用例")
    
    if cases:
        case = cases[0]
        print(f"\n第一条用例详情:")
        print(f"  Case ID: {case.case_id}")
        print(f"  Target Agent: {case.target_agent}")
        print(f"  Scene: {case.scene_description}")
        print(f"  Workflow Type: {case.get_workflow_type().value}")
        print(f"  Input Query: {case.input_query[:50]}...")
        print(f"  Dynamic Inputs: {list(case.dynamic_inputs.keys())}")
        print(f"  Expected Action: {case.expected_action}")
        print(f"  Session Key: {case.session_key}")
        
        # 验证是否为Chat类型
        assert case.get_workflow_type() == WorkflowType.CHAT, "应该是Chat类型"
        print("\n✅ 验证通过: 正确识别为Chat类型")
    
    return True

def test_load_xiaofang_fz_cases():
    """测试加载 xiaofang_fz_todo.csv"""
    print("\n" + "="*60)
    print("测试2: 加载 xiaofang_fz_todo.csv")
    print("="*60)
    
    loader = CaseLoader(data_dir="src/data")
    cases = loader.load_cases("xiaofang_fz_todo.csv")
    
    print(f"✅ 加载了 {len(cases)} 条用例")
    
    if cases:
        case = cases[0]
        print(f"\n第一条用例详情:")
        print(f"  Case ID: {case.case_id}")
        print(f"  Target Agent: {case.target_agent}")
        print(f"  Scene: {case.scene_description}")
        print(f"  Workflow Type: {case.get_workflow_type().value}")
        print(f"  Has Order Detail: {case.order_detail is not None}")
        print(f"  Has Chat History: {case.chat_history is not None}")
        print(f"  Dynamic Inputs: {list(case.dynamic_inputs.keys())}")
        
        # 验证是否为Workflow类型
        assert case.get_workflow_type() == WorkflowType.WORKFLOW, "应该是Workflow类型"
        print("\n✅ 验证通过: 正确识别为Workflow类型")
        
        # 验证Order_Detail是否正确解析
        if case.order_detail:
            print(f"\n✅ Order_Detail 已正确解析为字典对象")
            print(f"  Order_Detail keys: {list(case.order_detail.keys())[:5]}")
    
    return True

def test_filter_by_agent():
    """测试按智能体过滤"""
    print("\n" + "="*60)
    print("测试3: 按智能体过滤")
    print("="*60)
    
    loader = CaseLoader(data_dir="src/data")
    
    # 加载所有用例
    all_cases = loader.load_cases("xiaofang_fz_chat.csv")
    print(f"总用例数: {len(all_cases)}")
    
    # 只加载 follow_up 智能体的用例
    filtered_cases = loader.load_cases(
        "xiaofang_fz_chat.csv",
        case_filter={"target_agents": ["follow_up"]}
    )
    print(f"过滤后用例数: {len(filtered_cases)}")
    
    # 验证所有用例都是 follow_up
    for case in filtered_cases:
        assert case.target_agent == "follow_up", f"过滤失败: {case.target_agent}"
    
    print("✅ 验证通过: 过滤器正常工作")
    
    return True

def test_request_params_construction():
    """测试请求参数构造"""
    print("\n" + "="*60)
    print("测试4: 请求参数构造")
    print("="*60)
    
    from src.utils.test_executor import TestExecutor
    
    loader = CaseLoader(data_dir="src/data")
    
    # 测试Chat类型
    print("\n4.1 测试Chat类型参数构造:")
    chat_cases = loader.load_cases("xiaofang_fz_chat.csv")
    if chat_cases:
        case = chat_cases[0]
        executor = TestExecutor(None, None, {})
        params = executor._prepare_request(case)
        
        print(f"  Query: {params['query'][:50]}...")
        print(f"  Inputs keys: {list(params['inputs'].keys())}")
        print(f"  User: {params['user']}")
        print(f"  Has conversation_id: {'conversation_id' in params}")
        
        assert 'query' in params, "缺少query参数"
        assert 'inputs' in params, "缺少inputs参数"
        assert 'user' in params, "缺少user参数"
        assert 'conversation_id' in params, "Chat类型应该有conversation_id"
        print("  ✅ Chat类型参数构造正确")
    
    # 测试Workflow类型
    print("\n4.2 测试Workflow类型参数构造:")
    workflow_cases = loader.load_cases("xiaofang_fz_todo.csv")
    if workflow_cases:
        case = workflow_cases[0]
        executor = TestExecutor(None, None, {})
        params = executor._prepare_request(case)
        
        print(f"  Inputs keys: {list(params['inputs'].keys())}")
        print(f"  User: {params['user']}")
        print(f"  Has orderDetail: {'orderDetail' in params['inputs']}")
        print(f"  Has messages: {'messages' in params['inputs']}")
        
        assert 'inputs' in params, "缺少inputs参数"
        assert 'user' in params, "缺少user参数"
        
        # 验证orderDetail和messages是JSON字符串
        if 'orderDetail' in params['inputs']:
            assert isinstance(params['inputs']['orderDetail'], str), "orderDetail应该是JSON字符串"
            json.loads(params['inputs']['orderDetail'])  # 验证是否为有效JSON
            print("  ✅ orderDetail 正确转换为JSON字符串")
        
        if 'messages' in params['inputs']:
            assert isinstance(params['inputs']['messages'], str), "messages应该是JSON字符串"
            json.loads(params['inputs']['messages'])  # 验证是否为有效JSON
            print("  ✅ messages 正确转换为JSON字符串")
        
        print("  ✅ Workflow类型参数构造正确")
    
    return True

def main():
    """主函数"""
    print("\n" + "🚀 开始框架验证".center(60, "="))
    
    tests = [
        ("加载golden_dataset.csv", test_load_golden_dataset),
        ("加载xiaofang_fz_cases.csv", test_load_xiaofang_fz_cases),
        ("过滤器功能", test_filter_by_agent),
        ("请求参数构造", test_request_params_construction),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ 测试失败: {name}")
            print(f"   错误: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("="*60)
    
    if failed == 0:
        print("\n🎉 所有测试通过！框架工作正常！")
        return 0
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败，请检查")
        return 1

if __name__ == "__main__":
    sys.exit(main())

