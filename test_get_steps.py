"""
测试 get_steps_node 的运行结果
"""
from get_steps import get_steps_node
from schemas.state import AgentState


def test_get_steps_node():
    """测试 get_steps_node 是否正确读取 steps.txt 并写入 state.intent"""
    
    # 1. 初始化一个空的 AgentState
    initial_state: AgentState = {
        "intent": "",  # 初始为空
        "target_api": None,
        "candidate_apis": [],
        "used_apis": set(),
        "required_input_fields": set(),
        "available_output_fields": set(),
        "api_input_fields": {},
        "api_output_fields": {},
        "missing_fields": set(),
        "step_count": 0,
        "max_steps": 10,
    }
    
    print("=" * 60)
    print("测试 get_steps_node")
    print("=" * 60)
    print("\n初始状态:")
    print(f"  intent (长度): {len(initial_state['intent'])}")
    print(f"  intent 内容: {repr(initial_state['intent'][:50]) if initial_state['intent'] else '(空)'}")
    
    # 2. 调用 Node
    print("\n调用 get_steps_node...")
    result_state = get_steps_node(initial_state)
    
    # 3. 验证结果
    print("\n结果验证:")
    print(f"  intent 是否已更新: {result_state['intent'] != initial_state['intent']}")
    print(f"  intent 长度: {len(result_state['intent'])}")
    
    # 读取 steps.txt 进行对比
    import os
    expected_lines = []
    if os.path.exists("steps.txt"):
        with open("steps.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    expected_lines.append(line)
        expected_text = "\n".join(expected_lines)
        
        print("\n预期结果:")
        print(f"  预期行数: {len(expected_lines)}")
        print(f"  预期内容长度: {len(expected_text)}")
        
        print("\n实际结果:")
        print(f"  实际行数: {len(result_state['intent'].split(chr(10)))}")
        print(f"  实际内容长度: {len(result_state['intent'])}")
        
        # 验证内容是否匹配
        is_match = result_state['intent'] == expected_text
        print(f"\n内容匹配: {is_match}")
        
        if is_match:
            print("✅ 测试通过！Node 正确读取了 steps.txt 并写入 intent")
        else:
            print("❌ 测试失败！内容不匹配")
            print("\n预期内容前100字符:")
            print(repr(expected_text[:100]))
            print("\n实际内容前100字符:")
            print(repr(result_state['intent'][:100]))
    else:
        print("⚠️  警告: steps.txt 文件不存在，无法进行完整验证")
        if result_state['intent'] == "":
            print("✅ Node 正确处理了文件不存在的情况")
        else:
            print("❌ Node 应该返回空字符串，但实际返回了内容")
    
    # 4. 显示 intent 内容（前几行）
    print(f"\n{'=' * 60}")
    print("intent 内容预览（前5行）:")
    print("=" * 60)
    intent_lines = result_state['intent'].split('\n')
    for i, line in enumerate(intent_lines[:5], 1):
        print(f"  {i}. {line}")
    if len(intent_lines) > 5:
        print(f"  ... (共 {len(intent_lines)} 行)")
    
    # 5. 验证其他字段未被修改
    print(f"\n{'=' * 60}")
    print("验证其他字段未被修改:")
    print("=" * 60)
    fields_to_check = [
        "target_api", "candidate_apis", "used_apis", 
        "required_input_fields", "available_output_fields",
        "api_input_fields", "api_output_fields", "missing_fields",
        "step_count", "max_steps"
    ]
    all_unchanged = True
    for field in fields_to_check:
        initial_val = initial_state[field]
        result_val = result_state[field]
        unchanged = initial_val == result_val
        all_unchanged = all_unchanged and unchanged
        status = "✅" if unchanged else "❌"
        print(f"  {status} {field}: {unchanged}")
    
    if all_unchanged:
        print("\n✅ 所有其他字段保持不变，符合预期")
    else:
        print("\n❌ 某些字段被意外修改")
    
    return result_state


if __name__ == "__main__":
    test_get_steps_node()

