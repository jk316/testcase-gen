"""SDK 多攻击组装 + 代码合成器的单元测试。"""
import ast

from codegen.ir import (
    AttackSpec,
    BusinessSpec,
    PlanStep,
    Ref,
    TestRequirement,
    validate_plan,
)
from codegen.synthesizer import synthesize
from examples.sdk import AlpsClient
from examples.sdk.capabilities import CAPABILITIES


def _requirement() -> TestRequirement:
    return TestRequirement(
        name="UDP+HTTP 混合攻击",
        duration_sec=200,
        attacks=(
            AttackSpec(type="udp_flood", bandwidth_mbps=500, target={"dest_ip": "11.0.0.1/24"}),
            AttackSpec(type="http_get_flood", bandwidth_mbps=500, target={"url": "http://x/i"}),
        ),
        businesses=(BusinessSpec(type="http_browse", bandwidth_mbps=2000),),
    )


def _plan() -> list[PlanStep]:
    return [
        PlanStep("login", "login", {}, ["session_id"]),
        PlanStep("reserve", "reserve_port", {"port_id": "port_1"}, []),
        PlanStep("prof_udp", "ensure_attack_profile", {"profile_name": "udp_flood"}, ["profile_id", "profile_name"]),
        PlanStep("prof_http", "ensure_attack_profile", {"profile_name": "http_get_flood"}, ["profile_id", "profile_name"]),
        PlanStep("prof_biz", "ensure_load_profile", {"profile_name": "http_browse"}, ["profile_id", "profile_name"]),
        PlanStep("tc", "create_testcase", {"testcase_name": "UDP+HTTP 混合攻击"}, ["testcase_id"]),
        PlanStep(
            "build",
            "build_testcase_info",
            {"testcase_id": Ref("tc", "testcase_id"), "testcase_name": "UDP+HTTP 混合攻击"},
            ["testcase_info"],
        ),
        PlanStep(
            "save",
            "save_testcase",
            {"testcase_id": Ref("tc", "testcase_id"), "testcase_info": Ref("build", "testcase_info")},
            [],
        ),
        PlanStep(
            "run",
            "run_testcase",
            {"testcase_id": Ref("tc", "testcase_id"), "testcase_name": "UDP+HTTP 混合攻击"},
            [],
        ),
        PlanStep("stats", "get_stats_overview", {"instance_id": Ref("tc", "testcase_id")}, []),
        PlanStep("logout", "logout", {}, []),
    ]


def test_set_testcase_info_multi_attack_and_business():
    client = AlpsClient(base_url="https://x", name="admin", password="admin", verify=False)
    info = client.set_testcase_info(
        1,
        "t",
        attacks=[
            {"profile_id": 10, "profile_name": "udp_flood", "bandwidth_mbps": 500, "duration_sec": 200},
            {"profile_id": 11, "profile_name": "http_get_flood", "bandwidth_mbps": 500, "duration_sec": 200},
        ],
        businesses=[{"profile_id": 20, "profile_name": "http_browse", "bandwidth_mbps": 2000, "duration_sec": 200}],
    )
    assert len(info.ddos_attack_list) == 2
    assert len(info.app_simulator_list) == 1
    assert info.ddos_attack_list[0].data_rate.min_rate == 500
    assert info.ddos_attack_list[0].load_profile.default.steady.duration == 200
    assert info.app_simulator_list[0].app_profile.profile_id == 20


def test_synthesize_generates_valid_python():
    plan = _plan()
    assert validate_plan(plan, CAPABILITIES) == []
    code = synthesize(_requirement(), plan)
    ast.parse(code)  # 语法合法


def test_synthesize_injects_bandwidth_and_business():
    code = synthesize(_requirement(), _plan())
    assert "'bandwidth_mbps': 500" in code
    assert "'bandwidth_mbps': 2000" in code
    assert "client.set_testcase_info(" in code
    assert "attacks=ATTACKS, businesses=BUSINESSES" in code


def test_synthesize_resolves_refs():
    code = synthesize(_requirement(), _plan())
    # create_testcase 产出 testcase_id，run 引用它
    assert "v_tc_testcase_id = _r_tc[\"result\"][\"testcase_id\"]" in code
    assert "client.run_testcase(v_tc_testcase_id" in code
