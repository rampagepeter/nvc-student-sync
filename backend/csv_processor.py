import csv
import io
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import pandas as pd
from pydantic import BaseModel, validator

from .utils import validate_csv_headers, ProcessLogger

logger = logging.getLogger(__name__)

class StudentRecord(BaseModel):
    """学员记录模型"""
    user_id: str
    nickname: str
    phone: Optional[str] = None
    course: Optional[str] = None  # 改为可选
    learning_date: Optional[str] = None  # 改为可选
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if not v or not v.strip():
            raise ValueError('用户ID不能为空')
        return v.strip()
    
    @validator('nickname')
    def validate_nickname(cls, v):
        if not v or not v.strip():
            raise ValueError('昵称不能为空')
        return v.strip()
    
    @validator('course')
    def validate_course(cls, v):
        if v and not v.strip():
            raise ValueError('课程名称不能为空字符串')
        return v.strip() if v else "基础信息导入"  # 提供默认值
    
    @validator('learning_date')
    def validate_learning_date(cls, v):
        if v and not v.strip():
            raise ValueError('学习日期不能为空字符串')
        # 如果没有提供学习日期，使用当前日期
        return v.strip() if v else datetime.now().strftime("%Y-%m-%d")

class CSVProcessor:
    """CSV处理器"""
    
    # 默认的CSV字段映射
    DEFAULT_FIELD_MAPPING = {
        'user_id': ['用户ID', 'user_id', 'User ID', 'userid'],
        'nickname': ['昵称', 'nickname', 'Nickname', '姓名', 'name', '用户昵称'],
        'phone': ['手机号', 'phone', 'Phone', '电话', 'mobile', '最近采集号码真实姓名'],
        'course': ['课程', 'course', 'Course', '课程名称', 'course_name'],
        'learning_date': ['学习日期', 'learning_date', 'Learning Date', '报名日期', 'register_date', '日期', 'date']
    }
    
    def __init__(self, field_mapping: Optional[Dict[str, List[str]]] = None):
        self.field_mapping = field_mapping or self.DEFAULT_FIELD_MAPPING
        self.process_logger = ProcessLogger("CSV处理")
    
    def detect_encoding(self, file_content: bytes) -> str:
        """检测文件编码"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']
        
        for encoding in encodings:
            try:
                file_content.decode(encoding)
                logger.info(f"检测到文件编码: {encoding}")
                return encoding
            except UnicodeDecodeError:
                continue
        
        # 如果都不行，默认使用utf-8
        logger.warning("无法检测文件编码，使用默认编码utf-8")
        return 'utf-8'
    
    def parse_csv_content(self, file_content: bytes, filename: str) -> List[Dict[str, Any]]:
        """解析CSV文件内容"""
        self.process_logger.start(f"解析CSV文件: {filename}")
        
        try:
            # 检测编码
            encoding = self.detect_encoding(file_content)
            
            # 解码文件内容
            try:
                text_content = file_content.decode(encoding)
            except UnicodeDecodeError as e:
                logger.error(f"文件解码失败: {e}")
                raise ValueError(f"文件编码错误，无法解析: {e}")
            
            # 使用pandas读取CSV
            try:
                df = pd.read_csv(io.StringIO(text_content))
                self.process_logger.step(f"成功读取CSV文件，共{len(df)}行数据")
                
                # 转换为字典列表
                records = df.to_dict('records')
                
                # 清理数据
                cleaned_records = []
                for record in records:
                    # 移除空值和NaN
                    cleaned_record = {}
                    for key, value in record.items():
                        if pd.notna(value) and str(value).strip():
                            cleaned_record[key] = str(value).strip()
                    
                    if cleaned_record:  # 只保留非空记录
                        cleaned_records.append(cleaned_record)
                
                self.process_logger.step(f"数据清理完成，有效记录: {len(cleaned_records)}行")
                return cleaned_records
                
            except Exception as e:
                logger.error(f"CSV解析失败: {e}")
                raise ValueError(f"CSV文件格式错误: {e}")
                
        except Exception as e:
            self.process_logger.error(f"CSV解析失败: {e}")
            raise
    
    def map_fields(self, raw_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """映射字段名称"""
        if not raw_records:
            return {"mapped_records": [], "field_mapping": {}, "missing_fields": []}
        
        # 获取CSV文件的字段名
        csv_headers = list(raw_records[0].keys())
        logger.info(f"CSV文件字段: {csv_headers}")
        
        # 建立字段映射
        field_map = {}
        missing_fields = []
        
        for standard_field, possible_names in self.field_mapping.items():
            found = False
            for csv_header in csv_headers:
                if csv_header in possible_names:
                    field_map[standard_field] = csv_header
                    found = True
                    break
            
            if not found:
                missing_fields.append(standard_field)
        
        logger.info(f"字段映射: {field_map}")
        
        if missing_fields:
            logger.warning(f"缺少字段: {missing_fields}")
        
        # 映射数据
        mapped_records = []
        for record in raw_records:
            mapped_record = {}
            for standard_field, csv_field in field_map.items():
                if csv_field in record:
                    mapped_record[standard_field] = record[csv_field]
            
            if mapped_record:
                mapped_records.append(mapped_record)
        
        return {
            "mapped_records": mapped_records,
            "field_mapping": field_map,
            "missing_fields": missing_fields
        }
    
    def validate_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """验证记录数据"""
        valid_records = []
        invalid_records = []
        
        for i, record in enumerate(records):
            try:
                # 使用Pydantic模型验证
                student_record = StudentRecord(**record)
                valid_records.append(student_record.dict())
                
            except Exception as e:
                logger.warning(f"第{i+1}行数据验证失败: {e}")
                invalid_records.append({
                    "row": i + 1,
                    "record": record,
                    "error": str(e)
                })
        
        return {
            "valid_records": valid_records,
            "invalid_records": invalid_records,
            "valid_count": len(valid_records),
            "invalid_count": len(invalid_records)
        }
    
    def extract_unique_students(self, records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """提取唯一学员信息，保留所有CSV字段"""
        unique_students = {}
        
        for record in records:
            user_id = record['user_id']
            if user_id not in unique_students:
                # 保留所有字段，不仅仅是核心字段
                unique_students[user_id] = {
                    'user_id': user_id,
                    'nickname': record['nickname'],
                    'phone': record.get('phone', ''),
                    'csv_all_fields': record  # 保留完整的CSV记录
                }
            else:
                # 如果有更完整的信息，更新记录
                existing = unique_students[user_id]
                if not existing.get('phone') and record.get('phone'):
                    existing['phone'] = record['phone']
                
                # 如果昵称不同，记录警告
                if existing['nickname'] != record['nickname']:
                    logger.warning(f"用户{user_id}的昵称不一致: {existing['nickname']} vs {record['nickname']}")
                
                # 合并所有字段，新数据优先
                existing_csv_fields = existing.get('csv_all_fields', {})
                for key, value in record.items():
                    if value and (not existing_csv_fields.get(key) or existing_csv_fields[key] != value):
                        existing_csv_fields[key] = value
                existing['csv_all_fields'] = existing_csv_fields
        
        logger.info(f"提取到{len(unique_students)}个唯一学员")
        return unique_students
    
    def extract_unique_students_with_raw_data(self, valid_records: List[Dict[str, Any]], raw_records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """提取唯一学员信息，同时传入原始记录以保留所有字段"""
        unique_students = {}
        
        # 构建原始记录的用户ID映射
        raw_records_map = {}
        for raw_record in raw_records:
            # 查找原始记录中的用户ID字段
            user_id_field = None
            for field_name in ['用户ID', 'user_id', 'User ID', 'UserID']:
                if field_name in raw_record:
                    user_id_field = field_name
                    break
            
            if user_id_field and raw_record[user_id_field]:
                user_id = raw_record[user_id_field]
                if user_id not in raw_records_map:
                    raw_records_map[user_id] = []
                raw_records_map[user_id].append(raw_record)
        
        for record in valid_records:
            user_id = record['user_id']
            if user_id not in unique_students:
                # 查找对应的原始记录
                raw_record = {}
                if user_id in raw_records_map:
                    # 取第一个匹配的原始记录
                    raw_record = raw_records_map[user_id][0]
                
                # 保留所有字段，不仅仅是核心字段
                unique_students[user_id] = {
                    'user_id': user_id,
                    'nickname': record['nickname'],
                    'phone': record.get('phone', ''),
                    'csv_all_fields': raw_record  # 保留完整的原始CSV记录
                }
            else:
                # 如果有更完整的信息，更新记录
                existing = unique_students[user_id]
                if not existing.get('phone') and record.get('phone'):
                    existing['phone'] = record['phone']
                
                # 如果昵称不同，记录警告
                if existing['nickname'] != record['nickname']:
                    logger.warning(f"用户{user_id}的昵称不一致: {existing['nickname']} vs {record['nickname']}")
                
                # 合并原始记录字段
                if user_id in raw_records_map:
                    existing_csv_fields = existing.get('csv_all_fields', {})
                    for raw_record in raw_records_map[user_id]:
                        for key, value in raw_record.items():
                            if value and str(value).strip() and key not in existing_csv_fields:
                                existing_csv_fields[key] = value
                    existing['csv_all_fields'] = existing_csv_fields
        
        logger.info(f"提取到{len(unique_students)}个唯一学员")
        return unique_students
    
    def process_file(
        self, 
        file_content: bytes, 
        filename: str,
        course_name: str = None,
        learning_date: str = None
    ) -> Dict[str, Any]:
        """处理CSV文件的主要方法"""
        try:
            self.process_logger.start(f"处理CSV文件: {filename}")
            
            # 1. 解析CSV内容
            raw_records = self.parse_csv_content(file_content, filename)
            
            # 2. 映射字段
            mapping_result = self.map_fields(raw_records)
            mapped_records = mapping_result["mapped_records"]
            field_mapping = mapping_result["field_mapping"]
            missing_fields = mapping_result["missing_fields"]
            
            # 3. 应用手动输入的课程信息
            if course_name or learning_date:
                for record in mapped_records:
                    if course_name:
                        record['course'] = course_name
                    if learning_date:
                        record['learning_date'] = learning_date
            
            # 4. 验证数据
            validation_result = self.validate_records(mapped_records)
            valid_records = validation_result["valid_records"]
            invalid_records = validation_result["invalid_records"]
            
            # 5. 提取唯一学员 - 同时传入原始记录以保留所有字段
            unique_students = self.extract_unique_students_with_raw_data(
                valid_records, raw_records
            )
            
            # 6. 统计信息
            stats = {
                "total_rows": len(raw_records),
                "mapped_rows": len(mapped_records),
                "valid_rows": len(valid_records),
                "invalid_rows": len(invalid_records),
                "unique_students": len(unique_students),
                "learning_records": len(valid_records)
            }
            
            self.process_logger.finish(
                f"处理完成: {stats['valid_rows']}/{stats['total_rows']} 有效记录，"
                f"{stats['unique_students']} 个学员，{stats['learning_records']} 条学习记录"
            )
            
            return {
                "success": True,
                "stats": stats,
                "unique_students": unique_students,
                "learning_records": valid_records,
                "field_mapping": field_mapping,
                "missing_fields": missing_fields,
                "invalid_records": invalid_records,
                "course_name": course_name,
                "learning_date": learning_date
            }
            
        except Exception as e:
            self.process_logger.error(f"文件处理失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_sample_csv(self) -> str:
        """生成示例CSV文件内容"""
        sample_data = [
            ["用户ID", "昵称", "手机号", "课程", "学习日期"],
            ["001", "张三", "13800138000", "NVC基础课程", "2024-01-15"],
            ["002", "李四", "13800138001", "NVC进阶课程", "2024-01-16"],
            ["001", "张三", "13800138000", "NVC进阶课程", "2024-01-20"],
            ["003", "王五", "13800138002", "NVC基础课程", "2024-01-18"]
        ]
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(sample_data)
        
        return output.getvalue()

# 工具函数
def create_csv_processor(field_mapping: Optional[Dict[str, List[str]]] = None) -> CSVProcessor:
    """创建CSV处理器实例"""
    return CSVProcessor(field_mapping)

def validate_csv_file(file_content: bytes, filename: str) -> Dict[str, Any]:
    """验证CSV文件格式"""
    processor = CSVProcessor()
    
    try:
        # 只进行基本的解析验证，不做完整处理
        encoding = processor.detect_encoding(file_content)
        text_content = file_content.decode(encoding)
        
        # 检查是否为有效的CSV
        df = pd.read_csv(io.StringIO(text_content), nrows=5)  # 只读前5行
        
        headers = df.columns.tolist()
        
        return {
            "valid": True,
            "headers": headers,
            "encoding": encoding,
            "preview_rows": len(df)
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        } 