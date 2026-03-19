"""
工具函数模块
"""
import os
from dotenv import load_dotenv
from datetime import datetime
import logging

# 加载环境变量
load_dotenv()

def setup_logger(name: str = __name__) -> logging.Logger:
    """设置日志记录器"""
    logger = logging.Logger(name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

def get_env(key: str, default: str = None) -> str:
    """获取环境变量"""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"环境变量 {key} 未设置")
    return value

def get_date_str() -> str:
    """获取当前日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")

def get_datetime_str() -> str:
    """获取当前日期时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
