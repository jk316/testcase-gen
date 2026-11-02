"""端到端执行验证：生成的脚本在 mock 客户端上完整执行，校验调用序列。"""
from unittest.mock import patch

import examples.sdk.client as sdk_client
from codegen.ir import (
    AttackSpec,
    BusinessSpec,
    PlanStep,
    Ref,
    TestRequirement,
)
from codegen.synthesizer import synthesize

# 各接口的 mock 返回；udp_flood 走复用，http_get_flood/business 走新建
RESPONSES = {
    "/v1/cl/user/login": {"result": {"session_id": "sess_123"}},
    "/v1/cl/network/list": {
        "result": [
            {"network_id": 18, "network_name": "ZGC Scene Two Network"},
            {"network_id": 17, "network_name": "ZGC Scene One Network"},
        ]
    },
    "/v1/cl/network/tags/fetch": {"code": 0, "result": ["client9", "server9"]},
    "/v1/cl/ddos/attack/profile/list": {
        "result": [
            {"profile_id": 7, "profile_name": "UDP Flood Attack"},
            {"profile_id": 8, "profile_name": "HTTP GET Flood Attack"},
        ]
    },
    "/v1/cl/ddos/attack/profile/create": {"result": {"profile_id": 99}},
    "/v1/cl/load/profile/list": {
        "result": [{"profile_id": 10, "profile_name": "HTTP Browse Profile"}]
    },
    "/v1/cl/load/profile/create": {"result": {"profile_id": 100}},
    "/v1/cl/testcase/create": {"result": {"testcase_id": 10850}},
    "/v1/cl/testcase/save": {"result": {}},
    "/v1/cl/testcase/run": {"result": {"instance_id": 500}},
    "/v1/cl/testcase/status": {
        "result": {"instance_id": 500, "duration": 0, "is_running": True}
    },
    "/v1/cl/stats/overview": {"result": {"bandwidth": 1000}},
    "/v1/cl/testcase/stop": {"result": {}},
    "/v1/cl/user/logout": {"result": {}},
}


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
        PlanStep("login", "login", {}, []),
        PlanStep("network", "select_network", {}, []),
        PlanStep("prof_udp", "ensure_attack_profile", {"profile_name": "udp_flood"}, []),
        PlanStep("prof_http", "ensure_attack_profile", {"profile_name": "http_get_flood"}, []),
        PlanStep("prof_biz", "ensure_load_profile", {"profile_name": "http_browse"}, []),
        PlanStep("tc", "create_testcase", {"testcase_name": "UDP+HTTP 混合攻击"}, []),
        PlanStep(
            "build",
            "build_testcase_info",
            {
                "testcase_id": Ref("tc", "testcase_id"),
                "testcase_name": "UDP+HTTP 混合攻击",
                "network_id": Ref("network", "network_id"),
                "network_name": Ref("network", "network_name"),
            },
            [],
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
        PlanStep("stats", "get_stats_overview", {"instance_id": Ref("run", "instance_id")}, []),
        PlanStep("stop", "stop_testcase", {"testcase_id": Ref("tc", "testcase_id")}, []),
        PlanStep("logout", "logout", {}, []),
    ]


def _execute(code: str) -> list[tuple[str, str, dict]]:
    calls: list[tuple[str, str, dict]] = []

    def fake_request(self, method, path, *, params=None, json_body=None, **kw):
        calls.append((method, path, json_body or {}))
        return RESPONSES.get(path, {"result": {}})

    ns: dict = {}
    with patch.object(sdk_client.AlpsClient, "_request", fake_request):
        exec(compile(code, "<generated>", "exec"), ns)
        ns["main"]()
    return calls


def test_generated_script_executes_end_to_end():
    code = synthesize(_requirement(), _plan())
    calls = _execute(code)

    paths = [path for _, path, _ in calls]
    # 起止与会话
    assert paths[0] == "/v1/cl/user/login"
    assert paths[-1] == "/v1/cl/user/logout"

    # 网络邻居：只查询并选择，不预约端口
    assert "/v1/cl/network/list" in paths
    assert "/v1/cl/port/list" not in paths
    assert "/v1/cl/port/reserve" not in paths

    # profile：只搜索并复用相似名称，不创建空配置
    assert paths.count("/v1/cl/ddos/attack/profile/list") == 2
    assert "/v1/cl/ddos/attack/profile/create" not in paths
    assert "/v1/cl/load/profile/list" in paths
    assert "/v1/cl/load/profile/create" not in paths

    # 测试用例：创建→保存→运行→统计→停止
    for p in (
        "/v1/cl/testcase/create",
        "/v1/cl/testcase/save",
        "/v1/cl/testcase/run",
        "/v1/cl/stats/overview",
        "/v1/cl/testcase/stop",
    ):
        assert p in paths


def test_save_body_has_multi_attack_and_business():
    code = synthesize(_requirement(), _plan())
    calls = _execute(code)

    save_body = next(body for _, path, body in calls if path == "/v1/cl/testcase/save")
    info = save_body["testcase_info"]
    assert len(info["ddos_attack_list"]) == 2
    assert len(info["app_simulator_list"]) == 1
    # 带宽已注入
    assert info["ddos_attack_list"][0]["data_rate"]["min_rate"] == 500
    assert info["app_simulator_list"][0]["data_rate"]["min_rate"] == 2000
    assert info["shared_settings"]["network_id"] == 17
    assert info["shared_settings"]["network_name"] == "ZGC Scene One Network"
    assert info["shared_settings"]["testcase_name"].startswith("AI")
    assert info["component_tags"] == ["client9", "server9"]
    assert info["ddos_attack_list"][0]["basic"]["client_tags"] == ["client9"]
    assert info["ddos_attack_list"][0]["basic"]["server_tags"] == ["server9"]
    # 时长已注入
    assert info["ddos_attack_list"][0]["load_profile"]["default"]["steady"]["duration"] == 200


def test_stats_uses_run_instance_id():
    code = synthesize(_requirement(), _plan())
    calls = _execute(code)

    run_body = next(body for _, path, body in calls if path == "/v1/cl/testcase/run")
    create_body = next(body for _, path, body in calls if path == "/v1/cl/testcase/create")
    stats_body = next(body for _, path, body in calls if path == "/v1/cl/stats/overview")
    # run 返回 instance_id=500，stats 必须引用它（而非 testcase_id）
    assert stats_body["instance_id"] == 500
    assert stats_body["interval"] == 1
    assert run_body["testcase_id"] == 10850
    assert create_body["testcase_name"].startswith("AI")
    assert run_body["testcase_name"].startswith("AI")


def test_run_falls_back_to_status_when_response_has_no_result():
    responses = dict(RESPONSES)
    responses["/v1/cl/testcase/run"] = {"code": 0, "message": "success"}
    calls: list[tuple[str, str, dict]] = []

    def fake_request(self, method, path, *, params=None, json_body=None, **kw):
        calls.append((method, path, json_body or {}))
        return responses.get(path, {"result": {}})

    client = sdk_client.AlpsClient(
        base_url="https://x", name="admin", password="admin", verify=False
    )
    client.session_id = "sess_123"
    with patch.object(sdk_client.AlpsClient, "_request", fake_request):
        result = client.run_testcase(10850, "t", instance_lookup_timeout=0)

    assert result["result"]["instance_id"] == 500
    assert [path for _, path, _ in calls] == [
        "/v1/cl/testcase/run",
        "/v1/cl/testcase/status",
    ]
