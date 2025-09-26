import os
import json
import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, validator
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)

class FieldMapping(BaseModel):
    """字段映射配置"""
    text_field: Optional[str] = None
    image_field: Optional[str] = None
    comment_field: Optional[str] = None
    submitter_field: Optional[str] = None
    time_field: Optional[str] = None

class TableConfig(BaseModel):
    """表格配置"""
    id: str
    name: str
    app_token: str
    table_id: str
    field_mapping: FieldMapping
    
    @validator('app_token', 'table_id')
    def validate_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('app_token和table_id不能为空')
        return v.strip()

class AppConfig(BaseModel):
    """应用配置"""
    feishu_app_id: str
    feishu_app_secret: str
    student_table: TableConfig  # 学员总表
    learning_record_table: TableConfig  # 学习记录表
    
    @validator('feishu_app_id', 'feishu_app_secret')
    def validate_credentials(cls, v):
        if not v or not v.strip():
            raise ValueError('飞书应用凭证不能为空')
        return v.strip()

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "config/config.json"):
        self.config_file = config_file
        self._config: Optional[AppConfig] = None
    
    def load_config(self) -> AppConfig:
        """加载配置"""
        try:
            # 优先从环境变量读取
            feishu_app_id = os.getenv('FEISHU_APP_ID', '')
            feishu_app_secret = os.getenv('FEISHU_APP_SECRET', '')
            
            # 从JSON文件读取表格配置
            config_data = self._load_json_config()
            
            # 合并配置
            config_data['feishu_app_id'] = feishu_app_id or config_data.get('feishu_app_id', '')
            config_data['feishu_app_secret'] = feishu_app_secret or config_data.get('feishu_app_secret', '')
            
            self._config = AppConfig(**config_data)
            logger.info("配置加载成功")
            return self._config
            
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            raise
    
    def _load_json_config(self) -> Dict:
        """从JSON文件加载配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"配置文件 {self.config_file} 不存在，使用默认配置")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            raise
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "feishu_app_id": "",
            "feishu_app_secret": "",
            "student_table": {
                "id": "student_table",
                "name": "学员总表",
                "app_token": "",
                "table_id": "",
                "field_mapping": {
                    "text_field": "昵称",
                    "comment_field": "备注",
                    "submitter_field": "录入人",
                    "time_field": "录入时间"
                }
            },
            "learning_record_table": {
                "id": "learning_record_table", 
                "name": "学习记录表",
                "app_token": "",
                "table_id": "",
                "field_mapping": {
                    "text_field": "课程",
                    "comment_field": "备注",
                    "submitter_field": "录入人",
                    "time_field": "学习日期"
                }
            }
        }
    
    def save_config(self, config: AppConfig):
        """保存配置到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # 转换为字典（不包含敏感信息）
            config_dict = config.dict()
            config_dict['feishu_app_id'] = ''  # 不保存敏感信息到文件
            config_dict['feishu_app_secret'] = ''
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"配置已保存到 {self.config_file}")
        except Exception as e:
            logger.error(f"配置保存失败: {e}")
            raise
    
    def validate_config(self, config: AppConfig) -> Dict:
        """验证配置"""
        errors = []
        warnings = []
        
        # 验证基本配置
        if not config.feishu_app_id:
            errors.append("缺少飞书应用ID")
        
        if not config.feishu_app_secret:
            errors.append("缺少飞书应用密钥")
        
        # 验证表格配置
        for table_name, table_config in [
            ("学员总表", config.student_table),
            ("学习记录表", config.learning_record_table)
        ]:
            if not table_config.app_token:
                errors.append(f"{table_name}缺少应用令牌")
            
            if not table_config.table_id:
                errors.append(f"{table_name}缺少表格ID")
            
            # 检查字段映射
            mapping = table_config.field_mapping
            if not any([mapping.text_field, mapping.image_field]):
                warnings.append(f"{table_name}建议配置至少一个内容字段")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
    
    @property
    def config(self) -> Optional[AppConfig]:
        """获取当前配置"""
        return self._config

# 全局配置管理器实例
config_manager = ConfigManager() 