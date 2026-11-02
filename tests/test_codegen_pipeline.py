"""parser / planner 确定性部分的单元测试（不调用真实 LLM）。"""
from codegen.ir import Ref, validate_plan
from codegen.parser import _build_requirement
from codegen.planner import _build_plan
from examples.sdk.capabilities import CAPABILITIES


def test_build_requirement_mixed_attack_bandwidth_even_split():
    data = {
        "name": "混合攻击",
        "duration_sec": 200,
        "attack": {
            "total_bandwidth_mbps": 1000,
            "types": ["udp_flood", "http_get_flood"],
            "targets": {"udp_flood": {"dest_ip": "11.0.0.1/24"}},
        },
        "business": {"total_bandwidth_mbps": 2000, "types": ["http_browse"]},
    }
    req = _build_requirement(data)
    assert [a.bandwidth_mbps for a in req.attacks] == [500, 500]
    assert [b.bandwidth_mbps for b in req.businesses] == [2000]
    assert req.attacks[0].target == {"dest_ip": "11.0.0.1/24"}
    assert req.duration_sec == 200


def test_build_requirement_no_business():
    data = {
        "name": "单攻击",
        "duration_sec": 60,
        "attack": {"total_bandwidth_mbps": 500, "types": ["udp_flood"], "targets": {}},
        "business": {"total_bandwidth_mbps": 0, "types": []},
    }
    req = _build_requirement(data)
    assert len(req.attacks) == 1
    assert req.attacks[0].bandwidth_mbps == 500
    assert req.businesses == ()


def test_build_plan_constructs_ref():
    data = [
        {
            "step_id": "run",
            "capability": "run_testcase",
            "inputs": {"testcase_id": {"ref": "tc", "field": "testcase_id"}},
            "outputs": [],
        }
    ]
    plan = _build_plan(data)
    assert plan[0].inputs["testcase_id"] == Ref(step="tc", field="testcase_id")


def test_build_plan_literal_value_stays():
    data = [
        {
            "step_id": "tc",
            "capability": "create_testcase",
            "inputs": {"testcase_name": "t"},
            "outputs": [],
        }
    ]
    plan = _build_plan(data)
    assert plan[0].inputs["testcase_name"] == "t"


def test_end_to_end_plan_validates():
    plan = _build_plan(
        [
            {"step_id": "login", "capability": "login", "inputs": {}, "outputs": ["session_id"]},
            {
                "step_id": "tc",
                "capability": "create_testcase",
                "inputs": {"testcase_name": "t"},
                "outputs": ["testcase_id"],
            },
            {
                "step_id": "run",
                "capability": "run_testcase",
                "inputs": {
                    "testcase_id": {"ref": "tc", "field": "testcase_id"},
                    "testcase_name": "t",
                },
                "outputs": [],
            },
            {"step_id": "logout", "capability": "logout", "inputs": {}, "outputs": []},
        ]
    )
    assert validate_plan(plan, CAPABILITIES) == []
