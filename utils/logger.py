"""
日志工具模块
提供统一的日志配置和管理
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional
from pathlib import Path


# 全局 logger 配置状态
_logger_configured = False
_log_config = None


def _get_log_level(level_str: str) -> int:
    """将字符串日志级别转换为 logging 常量"""
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str.upper(), logging.INFO)


def _configure_logging(config=None):
    """
    配置根 logger（只配置一次）
    
    Args:
        config: LogConfig 对象，如果为 None 则使用默认配置
    """
    global _logger_configured, _log_config
    
    if _logger_configured:
        return
    
    # 延迟导入 config 以避免循环导入
    if config is None:
        try:
            from config import get_config
            app_config = get_config()
            config = app_config.log
        except (ImportError, AttributeError):
            # 如果无法导入配置，使用默认配置
            from dataclasses import dataclass
            from typing import Optional
            
            @dataclass
            class DefaultLogConfig:
                level: str = "INFO"
                format: str = "| %(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
                file_path: Optional[str] = "logs/app.log"
                file_mode: str = "a"
                max_bytes: int = 10 * 1024 * 1024
                backup_count: int = 5
                console_output: bool = True
            
            config = DefaultLogConfig()
    
    _log_config = config
    
    # 获取根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(_get_log_level(config.level))
    
    # 清除已有的 handlers（避免重复）
    root_logger.handlers.clear()
    
    # 创建格式化器
    formatter = logging.Formatter(config.format)
    
    # 添加控制台 handler
    if config.console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(_get_log_level(config.level))
        root_logger.addHandler(console_handler)
    
    # 添加文件 handler（如果配置了文件路径）
    if config.file_path:
        try:
            # 确保日志目录存在
            log_dir = Path(config.file_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 使用 RotatingFileHandler 支持日志轮转
            file_handler = RotatingFileHandler(
                config.file_path,
                mode=config.file_mode,
                maxBytes=config.max_bytes,
                backupCount=config.backup_count,
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(_get_log_level(config.level))
            root_logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            # 如果无法创建文件 handler，只输出警告到控制台
            print(f"Warning: Failed to create file logger: {e}", file=sys.stderr)
    
    _logger_configured = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取 logger 实例
    
    Args:
        name: logger 名称，通常使用 __name__。如果为 None，使用调用模块的名称
    
    Returns:
        logging.Logger 实例
    """
    # 确保日志已配置
    if not _logger_configured:
        _configure_logging()
    
    # 如果未提供名称，尝试从调用栈获取模块名
    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get("__name__", "unknown")
    
    # 获取 logger（会自动继承根 logger 的配置）
    logger = logging.getLogger(name)
    
    return logger
