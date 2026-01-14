"""
配置管理模块
统一管理文件路径和配置值
"""
from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class FilePaths:
    """文件路径配置"""
    # 输入文件
    intent_list_file: str = "intent.txt"
    steps_file: str = "steps.txt"
    api_openapi_file: str = "inputs/xrt_openapi.jsonl"
    
    # 输出文件
    generated_steps_file: str = "steps.json"
    api_descriptions_file: str = "outputs/api_descriptions.jsonl"
    generated_testcases_file: str = "outputs/generated_testcases.jsonl"
    experience_pool_file: str = "outputs/experience_pool.jsonl"
    experience_pool_label_file: str = "outputs/experience_pool_label.jsonl"
    
    # 模板文件
    gen_steps_template: str = "prompts/gen_steps.jinja"
    testcase_template: str = "prompts/testcase.jinja"
    intent_template: str = "prompts/intent.jinja"
    
    # 索引目录
    index_dir: str = "indexes/api_intent_faiss"


@dataclass
class ModelConfig:
    """模型配置"""
    llm_model: str = "qwen-max"
    embedding_model: str = "text-embedding-v1"


@dataclass
class IndexConfig:
    """索引配置"""
    top_k: int = 3
    experience_similarity_threshold: float = 0.9
    force_rebuild: bool = False


@dataclass
class GraphConfig:
    """图执行配置"""
    recursion_limit: int = 100
    max_steps: int = 100


@dataclass
class LogConfig:
    """日志配置"""
    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    file_path: Optional[str] = "logs/app.log"  # None 表示不输出到文件
    file_mode: str = "a"  # 'a' 追加, 'w' 覆盖
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5  # 保留的备份文件数量
    console_output: bool = True  # 是否输出到控制台


@dataclass
class AppConfig:
    """应用配置主类"""
    files: FilePaths = None
    model: ModelConfig = None
    index: IndexConfig = None
    graph: GraphConfig = None
    log: LogConfig = None
    
    def __post_init__(self):
        """初始化默认配置"""
        if self.files is None:
            self.files = FilePaths()
        if self.model is None:
            self.model = ModelConfig()
        if self.index is None:
            self.index = IndexConfig()
        if self.graph is None:
            self.graph = GraphConfig()
        if self.log is None:
            self.log = LogConfig()
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """从环境变量加载配置（可选）"""
        config = cls()
        
        # 从环境变量覆盖日志配置
        if os.getenv("LOG_LEVEL"):
            config.log.level = os.getenv("LOG_LEVEL")
        if os.getenv("LOG_FILE"):
            config.log.file_path = os.getenv("LOG_FILE")
        if os.getenv("LOG_CONSOLE"):
            config.log.console_output = os.getenv("LOG_CONSOLE").lower() in ("true", "1", "yes")
        
        # 可以从环境变量覆盖其他配置
        # 例如：
        # config.files.intent_file = os.getenv("INTENT_FILE", config.files.intent_file)
        # config.model.llm_model = os.getenv("LLM_MODEL", config.model.llm_model)
        
        return config


# 全局配置实例（单例模式）
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config


def set_config(config: AppConfig) -> None:
    """设置全局配置实例（用于测试或自定义配置）"""
    global _config
    _config = config
