"""codegen IR 确定性逻辑的单元测试。"""
from codegen.ir import (
    PlanStep,
    Ref,
    allocate_bandwidth,
    parse_bandwidth_mbps,
    validate_plan,
)
from examples.sdk.capabilities import CAPABILITIES


def test_parse_bandwidth_gbps():
    assert parse_bandwidth_mbps("1Gbps") == 1000
    assert parse_bandwidth_mbps("1.5Gbps") == 1500


def test_parse_bandwidth_mbps_default_unit():
    assert parse_bandwidth_mbps("500Mbps") == 500
    assert parse_bandwidth_mbps("1000") == 1000


def test_parse_bandwidth_invalid():
    import pytest

    with pytest.raises(ValueError):
        parse_bandwidth_mbps("abc")


def test_allocate_bandwidth_even():
    assert allocate_bandwidth(1000, 2) == [500, 500]


def test_allocate_bandwidth_remainder_to_front():
    assert allocate_bandwidth(1000, 3) == [334, 333, 333]


def test_allocate_bandwidth_zero_count():
    assert allocate_bandwidth(1000, 0) == []


def _plan():
    return [
        PlanStep("login", "login", {}, ["session_id"]),
        PlanStep(
            "reserve", "reserve_port", {"port_id": "port_1"}, []
        ),
        PlanStep(
            "run", "run_testcase", {"testcase_id": Ref("create_tc", "testcase_id")}, []
        ),
    ]


def test_validate_plan_valid():
    plan = [
        PlanStep("login", "login", {}, ["session_id"]),
        PlanStep("create_tc", "create_testcase", {"testcase_name": "t"}, ["testcase_id"]),
        PlanStep(
            "run",
            "run_testcase",
            {"testcase_id": Ref("create_tc", "testcase_id"), "testcase_name": "t"},
            [],
        ),
        PlanStep("logout", "logout", {}, []),
    ]
    assert validate_plan(plan, CAPABILITIES) == []


def test_validate_plan_unknown_capability():
    plan = [PlanStep("x", "no_such_cap", {}, [])]
    errors = validate_plan(plan, CAPABILITIES)
    assert any("未知能力" in e for e in errors)


def test_validate_plan_ref_to_missing_step():
    plan = [
        PlanStep("login", "login", {}, ["session_id"]),
        PlanStep(
            "run",
            "run_testcase",
            {"testcase_id": Ref("nope", "testcase_id")},
            [],
        ),
    ]
    errors = validate_plan(plan, CAPABILITIES)
    assert any("不存在的步骤" in e for e in errors)


def test_validate_plan_ref_to_missing_field():
    plan = [
        PlanStep("create_tc", "create_testcase", {"testcase_name": "t"}, ["testcase_id"]),
        PlanStep(
            "run",
            "run_testcase",
            {"testcase_id": Ref("create_tc", "wrong_field")},
            [],
        ),
    ]
    errors = validate_plan(plan, CAPABILITIES)
    assert any("未产出字段" in e for e in errors)


def test_validate_plan_unknown_input_field():
    # create_testcase 声明了 input_fields=("testcase_name",)，传入未声明字段应报错
    plan = [
        PlanStep("tc", "create_testcase", {"bogus": 1, "testcase_name": "t"}, []),
    ]
    errors = validate_plan(plan, CAPABILITIES)
    assert any("不在能力" in e for e in errors)
