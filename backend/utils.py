import os
import logging
import logging.handlers
from datetime import datetime
from typing import Any, Dict, Optional
import json

def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    console_output: bool = True,
    file_output: bool = True
) -> None:
    """配置日志系统"""
    
    # 创建日志目录
    if file_output:
        os.makedirs(log_dir, exist_ok=True)
    
    # 配置日志级别
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # 创建根日志器
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # 清除现有处理器
    logger.handlers.clear()
    
    # 定义日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台输出
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 文件输出
    if file_output:
        # 普通日志文件
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 错误日志文件
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'error.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

def sanitize_log_data(data: Any) -> Any:
    """脱敏日志数据"""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in ['token', 'secret', 'password', 'key']):
                if isinstance(value, str) and len(value) > 10:
                    sanitized[key] = f"{value[:4]}...{value[-4:]}"
                else:
                    sanitized[key] = "***"
            else:
                sanitized[key] = sanitize_log_data(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_log_data(item) for item in data]
    else:
        return data

def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def format_duration(seconds: float) -> str:
    """格式化持续时间"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"

def validate_csv_headers(headers: list, required_fields: list) -> Dict[str, Any]:
    """验证CSV文件头"""
    missing_fields = []
    for field in required_fields:
        if field not in headers:
            missing_fields.append(field)
    
    return {
        "valid": len(missing_fields) == 0,
        "missing_fields": missing_fields,
        "headers": headers
    }

def create_response(
    success: bool,
    message: str,
    data: Optional[Any] = None,
    errors: Optional[list] = None
) -> Dict[str, Any]:
    """创建标准响应格式"""
    response = {
        "success": success,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    
    if data is not None:
        response["data"] = data
    
    if errors:
        response["errors"] = errors
    
    return response

def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """安全的JSON解析"""
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default

def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."

class ProcessLogger:
    """处理过程日志记录器"""
    
    def __init__(self, process_name: str):
        self.process_name = process_name
        self.logger = logging.getLogger(f"process.{process_name}")
        self.start_time = None
        self.step_count = 0
        
    def start(self, message: str = ""):
        """开始处理"""
        self.start_time = datetime.now()
        self.step_count = 0
        msg = f"[{self.process_name}] 开始处理"
        if message:
            msg += f": {message}"
        self.logger.info(msg)
        
    def step(self, message: str, data: Optional[Dict] = None):
        """记录处理步骤"""
        self.step_count += 1
        msg = f"[{self.process_name}] 步骤{self.step_count}: {message}"
        if data:
            sanitized_data = sanitize_log_data(data)
            msg += f" - {sanitized_data}"
        self.logger.info(msg)
        
    def error(self, message: str, error: Optional[Exception] = None):
        """记录错误"""
        msg = f"[{self.process_name}] 错误: {message}"
        if error:
            msg += f" - {str(error)}"
        self.logger.error(msg)
        
    def finish(self, message: str = "", success: bool = True):
        """结束处理"""
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            duration_str = format_duration(duration)
        else:
            duration_str = "未知"
            
        status = "成功" if success else "失败"
        msg = f"[{self.process_name}] 处理{status}, 耗时: {duration_str}"
        if message:
            msg += f": {message}"
            
        if success:
            self.logger.info(msg)
        else:
            self.logger.error(msg)

# 常用的日志记录器
app_logger = logging.getLogger("app")
api_logger = logging.getLogger("api")
sync_logger = logging.getLogger("sync") 