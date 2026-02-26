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
    intent_list_file: str = "inputs/intent.txt"
    steps_file: str = "inputs/steps.txt"
    api_openapi_file: str = "inputs/xrt_openapi.jsonl"
    experience_pool_md_file: str = "inputs/experience_pool.md"
    standard_format_file: str = "examples/testcase_example.json"
    
    # 输出文件
    generated_steps_file: str = "outputs/steps.json"
    api_descriptions_file: str = "outputs/api_descriptions.jsonl"
    generated_testcases_file: str = "outputs/new_generated_testcase.jsonl"
    experience_pool_file: str = "outputs/experience_pool.jsonl"
    experience_pool_label_file: str = "outputs/experience_pool_label.jsonl"
    params_reasoning_jsonl_file: str = "outputs/params_reasoning.jsonl"
    finalized_testcases_dir: str = "outputs/finalized_testcases"
    merged_testcase_dir: str = "outputs/merged_testcase"
    
    # 模板文件
    gen_steps_template: str = "prompts/gen_steps.jinja"
    testcase_template: str = "prompts/testcase.jinja"
    intent_template: str = "prompts/intent.jinja"
    params_reasoning_template: str = "prompts/params_reasoning.jinja"
    final_testcase_template: str = "prompts/final_testcase.jinja"
    
    # 索引目录
    index_dir: str = "indexes/api_intent_faiss"


@dataclass
class ModelConfig:
    """模型配置"""
    # LLM 提供商选择：tongyi, glm, deepseek
    llm_provider: str = "tongyi"
    
    #Qwen model (通义)
    qwen_model: str = "qwen-max"

    #GLM model (智谱)
    glm_model: str = "glm-4.7"
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"  # 智谱 OpenAI 兼容端点
    glm_api_key: Optional[str] = None

    #DeepSeek model
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: Optional[str] = None

    #embedding model
    embedding_model: str = "text-embedding-v1"

    #embedding base url
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


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
    level: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    format: str = "| %(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
    file_path: Optional[str] = "logs/app.log"  # None 表示不输出到文件
    file_mode: str = "a"  # 'a' 追加, 'w' 覆盖
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5  # 保留的备份文件数量
    console_output: bool = True  # 是否输出到控制台


@dataclass
class RedisConfig:
    """Redis 配置"""
    remote_host: str = "10.99.80.159"
    local_host: str = "127.0.0.1" # 本地redis
    port: int = 6379
    password: Optional[str] = "abcd@123"
    db: int = 0
    decode_responses: bool = True  # 自动解码响应为字符串


@dataclass
class AppConfig:
    """应用配置主类"""
    files: FilePaths = None
    model: ModelConfig = None
    index: IndexConfig = None
    graph: GraphConfig = None
    log: LogConfig = None
    redis: RedisConfig = None
    
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
        if self.redis is None:
            self.redis = RedisConfig()
    
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
        
        # 从环境变量覆盖 Redis 配置
        if os.getenv("REDIS_HOST"):
            config.redis.host = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            try:
                config.redis.port = int(os.getenv("REDIS_PORT"))
            except ValueError:
                pass
        if os.getenv("REDIS_PASSWORD"):
            config.redis.password = os.getenv("REDIS_PASSWORD")
        if os.getenv("REDIS_DB"):
            try:
                config.redis.db = int(os.getenv("REDIS_DB"))
            except ValueError:
                pass
        
        # 从环境变量覆盖 LLM 配置
        if os.getenv("LLM_PROVIDER"):
            config.model.llm_provider = os.getenv("LLM_PROVIDER")
        if os.getenv("LLM_MODEL"):
            config.model.llm_model = os.getenv("LLM_MODEL")
        if os.getenv("GLM_API_KEY"):
            config.model.glm_api_key = os.getenv("GLM_API_KEY")
        if os.getenv("GLM_MODEL"):
            config.model.glm_model = os.getenv("GLM_MODEL")
        if os.getenv("GLM_BASE_URL"):
            config.model.glm_base_url = os.getenv("GLM_BASE_URL")
        if os.getenv("DEEPSEEK_API_KEY"):
            config.model.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        if os.getenv("DEEPSEEK_MODEL"):
            config.model.deepseek_model = os.getenv("DEEPSEEK_MODEL")
        if os.getenv("DEEPSEEK_BASE_URL"):
            config.model.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL")
        
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
