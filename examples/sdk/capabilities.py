"""能力注册表 —— 编排面。

每个能力把「一类测试操作」绑定到 SDK 的一个方法 + 一段代码模板。
编排层（LLM / 规划）只引用能力名（``Capability.name``），代码合成层据此渲染调用。

模板约定（``template`` 为 Jinja2 字符串）：
- ``{{ out }}`` 表示本步产出的结果变量（由合成层决定名字）；
- 其它 ``{{ var }}`` 表示本步的输入变量（已解析为常量或前序步骤引用）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Capability:
    name: str
    client_method: str
    api_path: str
    description: str
    input_fields: Tuple[str, ...] = ()
    output_fields: Tuple[str, ...] = ()
    template: str = ""


_CAPABILITIES: Tuple[Capability, ...] = (
    Capability(
        name="login",
        client_method="login",
        api_path="/v1/cl/user/login",
        description="登录系统，获取会话，为后续调用提供认证上下文",
        output_fields=("session_id",),
        template="{{ out }} = client.login()",
    ),
    Capability(
        name="reserve_port",
        client_method="reserve_port",
        api_path="/v1/cl/port/reserve",
        description="预留一个发流端口",
        input_fields=("port_id",),
        output_fields=(),
        template="{{ out }} = client.reserve_port({{ port_id }})",
    ),
    Capability(
        name="ensure_attack_profile",
        client_method="ensure_attack_profile",
        api_path="/v1/cl/ddos/attack/profile/list|create",
        description="复用优先：按名称匹配已有攻击 profile，否则新建（返回 profile_id）",
        input_fields=("profile_name",),
        output_fields=("profile_id", "profile_name"),
        template="{{ out }} = client.ensure_attack_profile({{ profile_name }})",
    ),
    Capability(
        name="ensure_load_profile",
        client_method="ensure_load_profile",
        api_path="/v1/cl/load/profile/list|create",
        description="复用优先：按名称匹配已有负载（业务）profile，否则新建（返回 profile_id）",
        input_fields=("profile_name",),
        output_fields=("profile_id", "profile_name"),
        template="{{ out }} = client.ensure_load_profile({{ profile_name }})",
    ),
    Capability(
        name="create_testcase",
        client_method="create_testcase",
        api_path="/v1/cl/testcase/create",
        description="创建一个测试用例（返回 testcase_id）",
        input_fields=("testcase_name",),
        output_fields=("testcase_id",),
        template="{{ out }} = client.create_testcase({{ testcase_name }})",
    ),
    Capability(
        name="build_testcase_info",
        client_method="set_testcase_info",
        api_path="/v1/cl/testcase/save",
        description="把攻击/业务 profile 组装成 TestcaseInfo（含带宽、时长等参数）",
        input_fields=("testcase_id", "testcase_name", "profile_id", "profile_name"),
        output_fields=("testcase_info",),
        template="{{ out }} = client.set_testcase_info({{ testcase_id }}, {{ testcase_name }}, {{ profile_id }}, {{ profile_name }})",
    ),
    Capability(
        name="save_testcase",
        client_method="save_testcase",
        api_path="/v1/cl/testcase/save",
        description="保存测试用例配置",
        input_fields=("testcase_id", "testcase_info"),
        output_fields=(),
        template="{{ out }} = client.save_testcase({{ testcase_id }}, {{ testcase_info }})",
    ),
    Capability(
        name="run_testcase",
        client_method="run_testcase",
        api_path="/v1/cl/testcase/run",
        description="执行测试用例",
        input_fields=("testcase_id", "testcase_name"),
        output_fields=(),
        template="{{ out }} = client.run_testcase({{ testcase_id }}, {{ testcase_name }})",
    ),
    Capability(
        name="get_stats_overview",
        client_method="get_stats_overview",
        api_path="/v1/cl/stats/overview",
        description="获取测试用例实例的概览统计（流量、带宽等）",
        input_fields=("instance_id",),
        output_fields=(),
        template="{{ out }} = client.get_stats_overview({{ instance_id }})",
    ),
    Capability(
        name="stop_testcase",
        client_method="stop_testcase",
        api_path="/v1/cl/testcase/stop",
        description="停止测试用例",
        input_fields=("testcase_id",),
        output_fields=(),
        template="{{ out }} = client.stop_testcase({{ testcase_id }})",
    ),
    Capability(
        name="logout",
        client_method="logout",
        api_path="/v1/cl/user/logout",
        description="退出登录，释放会话",
        output_fields=(),
        template="{{ out }} = client.logout()",
    ),
)


CAPABILITIES: Dict[str, Capability] = {c.name: c for c in _CAPABILITIES}


def get_capability(name: str) -> Capability:
    """按能力名取能力；不存在则抛 KeyError。"""
    return CAPABILITIES[name]


__all__ = ["Capability", "CAPABILITIES", "get_capability"]
