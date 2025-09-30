import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
import json
import time
import ssl
import certifi

from .utils import sanitize_log_data, ProcessLogger
from .config import AppConfig

logger = logging.getLogger(__name__)

class FeishuAPIError(Exception):
    """飞书API异常类"""
    def __init__(self, message: str, code: int = 0, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details

class TokenManager:
    """Token管理器"""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.access_token = None
        self.expire_time = 0
        self.refresh_lock = asyncio.Lock()
        
    async def get_token(self) -> str:
        """获取有效的访问令牌"""
        # 如果token还有效（提前5分钟刷新）
        if self.access_token and time.time() < self.expire_time - 300:
            return self.access_token
        
        async with self.refresh_lock:
            # 双重检查，避免并发刷新
            if self.access_token and time.time() < self.expire_time - 300:
                return self.access_token
            
            logger.info("Token过期或不存在，正在获取新token...")
            await self._refresh_token()
            return self.access_token
    
    async def _refresh_token(self):
        """刷新访问令牌"""
        url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"

        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }

        # 创建带证书的 SSL 上下文
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise FeishuAPIError(f"Token请求失败: {response.status} - {error_text}")
                    
                    data = await response.json()
                    
                    if data.get("code") != 0:
                        raise FeishuAPIError(f"Token获取失败: {data.get('msg', '未知错误')}", data.get("code"))
                    
                    self.access_token = data["app_access_token"]
                    self.expire_time = time.time() + data["expire"]
                    
                    logger.info(f"Token刷新成功，有效期至: {datetime.fromtimestamp(self.expire_time)}")
                    
            except aiohttp.ClientError as e:
                raise FeishuAPIError(f"网络请求失败: {str(e)}")

class FeishuClient:
    """飞书API客户端"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.token_manager = TokenManager(config.feishu_app_id, config.feishu_app_secret)
        self.base_url = "https://open.feishu.cn/open-apis"
        self.session = None
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        # 创建带证书的 SSL 上下文
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None
    ) -> Dict:
        """发送HTTP请求"""
        if not self.session:
            raise FeishuAPIError("客户端未初始化，请使用async with语句")
        
        token = await self.token_manager.get_token()
        
        # 构建请求头
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        if headers:
            request_headers.update(headers)
        
        # 构建URL
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # 记录请求信息（脱敏）
        logger.debug(f"请求 {method} {url}")
        if data:
            logger.debug(f"请求数据: {sanitize_log_data(data)}")
        
        try:
            async with self.session.request(
                method, url, 
                json=data, 
                params=params, 
                headers=request_headers
            ) as response:
                
                logger.debug(f"响应状态: {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    raise FeishuAPIError(f"请求失败: {response.status} - {error_text}")
                
                result = await response.json()
                
                if result.get("code") != 0:
                    raise FeishuAPIError(
                        f"API错误: {result.get('msg', '未知错误')}", 
                        result.get("code"),
                        result
                    )
                
                return result
                
        except aiohttp.ClientError as e:
            raise FeishuAPIError(f"网络请求失败: {str(e)}")
    
    async def test_connection(self) -> Dict:
        """测试连接"""
        try:
            token = await self.token_manager.get_token()
            return {
                "success": True,
                "message": "连接成功",
                "data": {
                    "has_token": bool(token),
                    "token_expire": datetime.fromtimestamp(self.token_manager.expire_time).isoformat()
                }
            }
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return {
                "success": False,
                "message": str(e)
            }
    
    # 表格字段操作
    async def get_table_fields(self, app_token: str, table_id: str) -> List[Dict]:
        """获取表格字段信息"""
        endpoint = f"bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        
        try:
            result = await self._make_request("GET", endpoint)
            fields = result.get("data", {}).get("items", [])
            
            logger.info(f"获取表格字段成功: {len(fields)}个字段")
            return fields
            
        except Exception as e:
            logger.error(f"获取表格字段失败: {e}")
            raise
    
    # 记录查询操作
    async def query_records(
        self, 
        app_token: str, 
        table_id: str, 
        filter_conditions: Optional[Union[str, Dict]] = None,
        page_size: int = 100,
        page_token: Optional[str] = None
    ) -> Dict:
        """查询记录"""
        endpoint = f"bitable/v1/apps/{app_token}/tables/{table_id}/records"
        
        params = {
            "page_size": page_size
        }
        
        if filter_conditions:
            if isinstance(filter_conditions, dict):
                # JSON格式的过滤条件，需要转换为字符串
                params["filter"] = json.dumps(filter_conditions)
            else:
                # 字符串格式的过滤条件
                params["filter"] = filter_conditions
        
        if page_token:
            params["page_token"] = page_token
        
        try:
            result = await self._make_request("GET", endpoint, params=params)
            
            records = result.get("data", {}).get("items", [])
            has_more = result.get("data", {}).get("has_more", False)
            next_page_token = result.get("data", {}).get("page_token")
            
            logger.info(f"查询记录成功: {len(records)}条记录")
            
            return {
                "records": records,
                "has_more": has_more,
                "page_token": next_page_token
            }
            
        except Exception as e:
            logger.error(f"查询记录失败: {e}")
            raise
    
    async def search_records_by_user_id(
        self, 
        app_token: str, 
        table_id: str, 
        user_id_field: str,
        user_id: str
    ) -> List[Dict]:
        """根据用户ID搜索记录"""
        # 由于飞书API的过滤条件语法复杂且不稳定，
        # 采用客户端过滤的方式：获取所有记录，然后在客户端进行过滤
        try:
            # 获取所有记录（分页处理）
            all_records = []
            page_token = None
            
            while True:
                result = await self.query_records(
                    app_token, 
                    table_id,
                    page_size=500,  # 增大页面大小以提高效率
                    page_token=page_token
                )
                
                records = result["records"]
                all_records.extend(records)
                
                # 检查是否有更多数据
                if not result.get("has_more", False):
                    break
                
                page_token = result.get("page_token")
                if not page_token:
                    break
            
            # 在客户端过滤匹配的记录
            matching_records = []
            for record in all_records:
                record_fields = record.get("fields", {})
                record_user_id = record_fields.get(user_id_field)
                
                if record_user_id == user_id:
                    matching_records.append(record)
            
            logger.info(f"客户端过滤找到 {len(matching_records)} 条匹配记录")
            return matching_records
            
        except Exception as e:
            logger.error(f"根据用户ID搜索记录失败: {e}")
            raise
    
    # 记录创建操作
    async def create_record(
        self, 
        app_token: str, 
        table_id: str, 
        fields: Dict[str, Any]
    ) -> Dict:
        """创建记录"""
        endpoint = f"bitable/v1/apps/{app_token}/tables/{table_id}/records"
        
        data = {
            "fields": fields
        }
        
        try:
            result = await self._make_request("POST", endpoint, data=data)
            
            record = result.get("data", {}).get("record", {})
            logger.info(f"创建记录成功: {record.get('record_id', 'unknown')}")
            
            return record
            
        except Exception as e:
            logger.error(f"创建记录失败: {e}")
            raise
    
    # 记录更新操作
    async def update_record(
        self, 
        app_token: str, 
        table_id: str, 
        record_id: str,
        fields: Dict[str, Any]
    ) -> Dict:
        """更新记录"""
        endpoint = f"bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        
        data = {
            "fields": fields
        }
        
        try:
            result = await self._make_request("PUT", endpoint, data=data)
            
            record = result.get("data", {}).get("record", {})
            logger.info(f"更新记录成功: {record_id}")
            
            return record
            
        except Exception as e:
            logger.error(f"更新记录失败: {e}")
            raise
    
    # 批量操作
    async def batch_create_records(
        self, 
        app_token: str, 
        table_id: str, 
        records: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> List[Dict]:
        """批量创建记录"""
        all_results = []
        
        # 分批处理
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            logger.info(f"处理批次 {i // batch_size + 1}: {len(batch)}条记录")
            
            batch_results = []
            for record_fields in batch:
                try:
                    result = await self.create_record(app_token, table_id, record_fields)
                    batch_results.append({
                        "success": True,
                        "record": result
                    })
                except Exception as e:
                    logger.error(f"批量创建记录失败: {e}")
                    batch_results.append({
                        "success": False,
                        "error": str(e),
                        "fields": record_fields
                    })
            
            all_results.extend(batch_results)
            
            # 避免请求过于频繁
            await asyncio.sleep(0.1)
        
        success_count = sum(1 for r in all_results if r["success"])
        logger.info(f"批量创建完成: {success_count}/{len(records)} 成功")
        
        return all_results

# 辅助函数
def create_link_field(record_id: str) -> List[str]:
    """创建关联字段格式"""
    # 飞书双向关联字段需要字符串数组格式，而不是对象数组
    return [record_id]

def format_date_field(date_str: str) -> int:
    """格式化日期字段为时间戳"""
    try:
        if isinstance(date_str, str):
            # 尝试解析常见的日期格式
            formats = [
                "%Y-%m-%d",
                "%Y/%m/%d", 
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S"
            ]
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return int(dt.timestamp() * 1000)  # 飞书使用毫秒时间戳
                except ValueError:
                    continue
        
        raise ValueError(f"无法解析日期格式: {date_str}")
        
    except Exception as e:
        logger.warning(f"日期格式化失败: {e}")
        return int(datetime.now().timestamp() * 1000)

# 飞书字段类型常量
class FieldType:
    TEXT = 1           # 多行文本
    NUMBER = 2         # 数字
    SINGLE_SELECT = 3  # 单选
    MULTI_SELECT = 4   # 多选
    DATE = 5           # 日期
    CHECKBOX = 7       # 复选框
    USER = 11          # 人员
    PHONE = 13         # 电话号码
    URL = 15           # 超链接
    ATTACHMENT = 17    # 附件
    SINGLE_LINE_TEXT = 1005  # 单行文本
    LINK = 1001        # 关联记录 