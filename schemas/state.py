"""
AgentState 类型定义
"""
from typing import List, Dict, Set, TypedDict, Optional, Any


class AgentState(TypedDict):
    """LangGraph 的状态类型定义"""
    
    # 循环控制
    intent_list: List[str]
    current_intent_index: int

    steps_list: List[str]
    current_step_index: int

    # 当前候选 API ID 列表
    candidate_api_ids: List[List[str]]

    # 字段信息
    required_input_fields: Set[str]
    available_output_fields: Set[str]

    # 中间产物
    api_input_fields: Dict[str, Set[str]]
    api_output_fields: Dict[str, Set[str]]

    # 控制信息
    missing_fields: Set[str]
    step_count: int
    max_steps: int

    # 生成的 testcase
    generated_testcase: Optional[Dict[str, Any]]
