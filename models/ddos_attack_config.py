from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional


# --------------------- 基础模型 ---------------------

class DataRate(BaseModel):
    unlimited: Optional[bool] = None
    unit: Optional[int] = None
    type: Optional[int] = None
    min_rate: Optional[int] = None
    max_rate: Optional[int] = None


class BasicData(BaseModel):
    name: Optional[str] = None
    desc: Optional[str] = None
    client_tags: Optional[List[str]] = None
    server_tags: Optional[List[str]] = None
    disable: Optional[bool] = None


class AttackProfileBrief(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    profile_id: Optional[int] = Field(None, alias="profile_id")
    profile_name: Optional[str] = Field(None, alias="profile_name")
    user_id: Optional[int] = Field(None, alias="user_id")


class FlowItem(BaseModel):
    flow_id: Optional[int] = None
    user_id: Optional[int] = None
    flow_name: Optional[str] = None
    session_num: Optional[int] = None
    pkt_bytes: Optional[int] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None


class ProfileDetail(BaseModel):
    name: Optional[str] = None
    desc: Optional[str] = None
    user_id: Optional[str] = None
    weight_for_type: Optional[int] = None
    weights: Optional[List[int]] = None
    flows: Optional[List[FlowItem]] = None
    enable_impairment: Optional[List[bool]] = None


class SuperFlow(BaseModel):
    load_profile_type: Optional[int] = None
    max_flows: Optional[int] = None
    max_flow_rate: Optional[int] = None
    max_flow_attempts: Optional[int] = None
    enable_conn_ctrl: Optional[bool] = None
    max_outstanding_conns: Optional[int] = None
    enable_bandwidth_ctrl: Optional[bool] = None
    enable_max_flows: Optional[bool] = None
    flow_timeout: Optional[int] = 2000


class Behav(BaseModel):
    behavior: Optional[int] = None
    duration: Optional[int] = None


class DefaultProfile(BaseModel):
    ramp_up: Optional[Behav] = None
    steady: Optional[Behav] = None
    ramp_down: Optional[Behav] = None


class LoadProfile(BaseModel):
    default: Optional[DefaultProfile] = None


class SrcPort(BaseModel):
    type: Optional[int] = None
    min: Optional[int] = None
    max: Optional[int] = None
    polling_mode: Optional[int] = None


# --------------------- AttackModule ---------------------

class AttackModule(BaseModel):
    basic: Optional[BasicData] = None
    load_profile: Optional[LoadProfile] = None
    attack_profile: Optional[AttackProfileBrief] = None
    data_rate: Optional[DataRate] = None
    super_flow: Optional[SuperFlow] = None
    src_port: Optional[SrcPort] = None

    delay_start: Optional[int] = None
    delay_start_hour: Optional[int] = None
    delay_start_minute: Optional[int] = None
    delay_start_second: Optional[int] = None


class AppProfileBrief(BaseModel):
    """业务（应用仿真）profile 的简要信息。"""

    profile_id: Optional[int] = None
    profile_name: Optional[str] = None
    user_id: Optional[int] = None


class AppModule(BaseModel):
    """业务（应用仿真）模块，结构与 AttackModule 平行。"""

    basic: Optional[BasicData] = None
    load_profile: Optional[LoadProfile] = None
    app_profile: Optional[AppProfileBrief] = None
    data_rate: Optional[DataRate] = None
    super_flow: Optional[SuperFlow] = None
    src_port: Optional[SrcPort] = None
    delay_start: Optional[int] = None
    delay_start_second: Optional[int] = None


# --------------------- Testcase ---------------------

class SharedSettings(BaseModel):
    network_id: Optional[int] = None
    network_name: Optional[str] = None
    testcase_name: Optional[str] = None
    testcase_desc: Optional[str] = None

    sample_interval: Optional[int] = 1
    enable_custom_stats: Optional[bool] = False
    enable_cpu_usage: Optional[bool] = False
    port_reset: Optional[bool] = True


class TestcaseInfo(BaseModel):
    testcase_id: Optional[int] = None
    ping_setting: Optional[object] = None
    user_id: Optional[int] = None

    component_tags: Optional[List[str]] = None
    ddos_attack_list: Optional[List[AttackModule]] = None
    app_simulator_list: Optional[List[AppModule]] = None
    shared_settings: Optional[SharedSettings] = None


class Testcase(BaseModel):
    testcase_id: Optional[int] = None
    dynamic_apply: Optional[bool] = None
    testcase_info: Optional[TestcaseInfo] = None


# class AppModule(BaseModel):
#     basic: Optional[BasicData] = None
#     load_profile: Optional[LoadProfile] = None
#     app_profile: Optional[AppProfileBrief] = None
#     data_rate: Optional[DataRate] = None
#     super_flow: Optional[SuperFlow] = None
#     src_port: Optional[SrcPort] = None

#     delay_start: Optional[int] = None
#     delay_start_second: Optional[int] = None

#     ipv4_configuration: Optional[Ipv4Configuration] = None
#     ipv6_configuration: Optional[Ipv6Configuration] = None
#     tcp_configuration: Optional[TcpConfiguration] = None
#     perf_configuration: Optional[PerfConfiguration] = None
#     impairment_configuration: Optional[ImpairmentConfiguration] = None

# class Ipv4Configuration(BaseModel):
#     type: Optional[int] = None
#     ttl: Optional[int] = None
#     tos: Optional[int] = None