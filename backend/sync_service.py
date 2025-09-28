import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from .config import AppConfig, TableConfig
from .feishu_client import FeishuClient, FeishuAPIError, create_link_field, format_date_field
from .csv_processor import CSVProcessor
from .utils import ProcessLogger, create_response
from .cache_manager import StudentCacheManager

logger = logging.getLogger(__name__)

class FieldConflict:
    """字段冲突信息"""
    def __init__(self, field_name: str, existing_value: Any, new_value: Any, user_id: str, nickname: str = None):
        self.field_name = field_name
        self.existing_value = existing_value
        self.new_value = new_value
        self.user_id = user_id
        self.nickname = nickname or user_id  # 如果没有昵称，使用用户ID
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "existing_value": self.existing_value,
            "new_value": self.new_value,
            "user_id": self.user_id,
            "nickname": self.nickname
        }

class FieldMappingService:
    """字段映射服务"""

    # 默认CSV字段名到飞书字段名的映射
    DEFAULT_FIELD_MAPPING = {
        "用户ID": "用户ID",
        "昵称": "昵称",
        "手机号": "手机号",
        "姓名": "姓名",
        "城市": "城市",
        "城 市": "城市",  # 处理空格情况
        "微信号": "微信号",
        "性别": "性别",
        "地址": "地址",
        "年龄": "年龄",
        "行业": "行业",
        # 可以根据需要添加更多映射
    }

    def __init__(self, custom_mapping: Dict[str, str] = None):
        self.conflicts = []
        self.skipped_fields = []
        self.updated_fields = []
        # 使用自定义映射或默认映射
        self.field_mapping = custom_mapping or self.DEFAULT_FIELD_MAPPING.copy()
    
    def map_csv_fields_to_feishu(self, csv_fields: Dict[str, Any], feishu_field_names: List[str]) -> Dict[str, Any]:
        """将CSV字段映射到飞书字段"""
        mapped_fields = {}
        
        for csv_field, value in csv_fields.items():
            # 跳过空值
            if not value or str(value).strip() == "":
                continue
                
            # 查找映射
            feishu_field = self.field_mapping.get(csv_field)

            # 如果没有找到直接映射，尝试解析带表格前缀的映射
            if not feishu_field and '.' in self.field_mapping.get(csv_field, ''):
                table_field = self.field_mapping.get(csv_field, '')
                if table_field.startswith('student.'):
                    feishu_field = table_field[8:]  # 移除 'student.' 前缀
                elif table_field.startswith('learning.'):
                    # 学习记录表的字段暂时跳过，在学习记录同步时处理
                    continue
            
            if feishu_field and feishu_field in feishu_field_names:
                # 先清理数据：去除前后空白字符
                cleaned_value = str(value).strip() if value is not None else ""

                # 跳过空值字段
                if not cleaned_value or cleaned_value.lower() in ['nan', 'null', 'none']:
                    self.skipped_fields.append(f"{csv_field} (空值)")
                    continue

                # 对特定字段进行特殊处理
                processed_value = cleaned_value

                if feishu_field == "年龄":
                    try:
                        # 检查是否为空或无效值
                        if not cleaned_value or cleaned_value.lower() in ['0', '']:
                            self.skipped_fields.append(f"{csv_field} (年龄为空，跳过)")
                            continue

                        # 将浮点数转换为整数
                        age_value = int(float(cleaned_value))

                        # 验证年龄范围（1-120）
                        if age_value < 1 or age_value > 120:
                            self.skipped_fields.append(f"{csv_field} (年龄超出范围: {age_value})")
                            continue

                        processed_value = age_value
                    except (ValueError, TypeError):
                        # 如果转换失败，跳过此字段
                        self.skipped_fields.append(f"{csv_field} (年龄格式错误: {cleaned_value})")
                        continue
                elif feishu_field == "手机号":
                    try:
                        # 去除手机号中的所有非数字字符
                        phone_digits = ''.join(filter(str.isdigit, cleaned_value))

                        # 如果没有数字，跳过
                        if not phone_digits:
                            self.skipped_fields.append(f"{csv_field} (手机号无数字: {cleaned_value})")
                            continue

                        # 验证手机号长度（通常11位）
                        if len(phone_digits) < 7 or len(phone_digits) > 15:
                            logger.warning(f"手机号长度异常: {phone_digits} (长度: {len(phone_digits)})")

                        processed_value = phone_digits
                    except Exception:
                        # 如果处理失败，跳过此字段
                        self.skipped_fields.append(f"{csv_field} (手机号处理失败: {cleaned_value})")
                        continue

                mapped_fields[feishu_field] = processed_value
                self.updated_fields.append(f"{csv_field} -> {feishu_field}")
            elif csv_field not in ["user_id", "nickname", "phone", "course", "learning_date"]:
                # 跳过处理过的核心字段和不存在的字段
                if feishu_field:
                    self.skipped_fields.append(f"{csv_field} (表格中无此字段: {feishu_field})")
                else:
                    self.skipped_fields.append(f"{csv_field} (无映射规则)")
        
        return mapped_fields
    
    def detect_conflicts(self, new_fields: Dict[str, Any], existing_record: Dict[str, Any], user_id: str, nickname: str = None) -> List[FieldConflict]:
        """检测字段冲突"""
        conflicts = []
        existing_fields = existing_record.get("fields", {})
        
        for field_name, new_value in new_fields.items():
            existing_value = existing_fields.get(field_name)
            
            # 如果现有值不为空且与新值不同，则认为是冲突
            if (existing_value and 
                str(existing_value).strip() != "" and 
                str(existing_value).strip() != str(new_value).strip()):
                
                conflict = FieldConflict(field_name, existing_value, new_value, user_id, nickname)
                conflicts.append(conflict)
                self.conflicts.append(conflict)
        
        return conflicts
    
    def get_summary(self) -> Dict[str, Any]:
        """获取字段处理摘要"""
        return {
            "updated_fields": self.updated_fields,
            "skipped_fields": self.skipped_fields,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "conflicts_count": len(self.conflicts),
            "updated_count": len(self.updated_fields),
            "skipped_count": len(self.skipped_fields)
        }

class SyncResult:
    """同步结果"""
    def __init__(self):
        self.total_records = 0
        self.processed_records = 0
        self.new_students = 0
        self.updated_students = 0
        self.new_learning_records = 0
        self.errors = []
        self.warnings = []
        self.start_time = datetime.now()
        self.end_time = None
        
        # 字段映射相关
        self.field_mapping_summary = None
        self.conflicts = []
        self.skipped_fields = []
        self.updated_fields = []
    
    def add_error(self, error: str):
        """添加错误"""
        self.errors.append(error)
        logger.error(error)
    
    def add_warning(self, warning: str):
        """添加警告"""
        self.warnings.append(warning)
        logger.warning(warning)
    
    def set_field_mapping_summary(self, field_mapping_service: 'FieldMappingService'):
        """设置字段映射摘要"""
        self.field_mapping_summary = field_mapping_service.get_summary()
        self.conflicts = self.field_mapping_summary['conflicts']
        self.skipped_fields = self.field_mapping_summary['skipped_fields']
        self.updated_fields = self.field_mapping_summary['updated_fields']
    
    def finish(self):
        """标记完成"""
        self.end_time = datetime.now()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取同步结果摘要"""
        duration = None
        if self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        
        summary = {
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "new_students": self.new_students,
            "updated_students": self.updated_students,
            "new_learning_records": self.new_learning_records,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_seconds": duration,
            "success_rate": self.processed_records / self.total_records if self.total_records > 0 else 0
        }
        
        # 添加字段映射信息
        if self.field_mapping_summary:
            summary.update({
                "field_mapping": self.field_mapping_summary,
                "has_conflicts": len(self.conflicts) > 0,
                "conflicts_count": len(self.conflicts),
                "updated_fields_count": len(self.updated_fields),
                "skipped_fields_count": len(self.skipped_fields)
            })
        
        return summary

class StudentSyncService:
    """学员同步服务"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.process_logger = ProcessLogger("学员同步")
        # TTL设置为10000小时（约416天），实际上缓存不会过期
        self.cache_manager = StudentCacheManager(cache_dir="cache", ttl_hours=10000)
        
    async def sync_csv_data(
        self,
        file_content: bytes,
        filename: str,
        course_name: str = None,
        learning_date: str = None,
        field_mapping: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """同步CSV数据到飞书表格"""
        result = SyncResult()
        
        try:
            self.process_logger.start(f"开始同步数据: {filename}")
            
            # 1. 处理CSV文件
            csv_processor = CSVProcessor()
            csv_result = csv_processor.process_file(
                file_content, 
                filename,
                course_name=course_name,
                learning_date=learning_date
            )
            
            if not csv_result["success"]:
                return create_response(
                    success=False,
                    message=f"CSV文件处理失败: {csv_result['error']}"
                )
            
            unique_students = csv_result["unique_students"]
            learning_records = csv_result["learning_records"]
            result.total_records = len(learning_records)
            
            self.process_logger.step(
                f"CSV处理完成: {len(unique_students)}个学员，{len(learning_records)}条学习记录"
            )
            
            # 2. 同步学员数据
            async with FeishuClient(self.config) as feishu_client:
                # 测试连接
                connection_test = await feishu_client.test_connection()
                if not connection_test["success"]:
                    return create_response(
                        success=False,
                        message=f"飞书连接失败: {connection_test['message']}"
                    )
                
                # 同步学员总表
                student_id_mapping = await self._sync_students(
                    feishu_client, unique_students, result, field_mapping
                )
                
                # 同步学习记录表
                await self._sync_learning_records(
                    feishu_client, learning_records, student_id_mapping, result
                )
            
            result.finish()
            self.process_logger.finish(
                f"同步完成: 新增{result.new_students}个学员，{result.new_learning_records}条学习记录"
            )

            # 保存缓存更新到文件
            await self.cache_manager.save_cache_updates()

            return create_response(
                success=True,
                message="数据同步完成",
                data=result.get_summary()
            )
            
        except Exception as e:
            result.add_error(f"同步过程发生异常: {str(e)}")
            self.process_logger.error(f"同步失败: {e}")
            
            return create_response(
                success=False,
                message=f"同步失败: {str(e)}",
                data=result.get_summary()
            )
    
    async def _sync_students(
        self,
        feishu_client: FeishuClient,
        unique_students: Dict[str, Dict[str, Any]],
        result: SyncResult,
        field_mapping: Dict[str, str] = None
    ) -> Dict[str, str]:
        """同步学员数据，返回用户ID到record_id的映射"""
        self.process_logger.step(f"开始同步学员数据: {len(unique_students)}个学员")
        
        student_table = self.config.student_table
        student_id_mapping = {}
        
        # 获取学员总表的字段信息，用于字段映射
        try:
            table_fields = await feishu_client.get_table_fields(
                student_table.app_token,
                student_table.table_id
            )
            feishu_field_names = [field["field_name"] for field in table_fields]
            self.process_logger.step(f"获取到学员总表字段: {len(feishu_field_names)}个")
        except Exception as e:
            result.add_error(f"获取表格字段失败: {str(e)}")
            feishu_field_names = []
        
        # 创建字段映射服务
        field_mapping_service = FieldMappingService(field_mapping)
        
        # 批量查询现有学员
        existing_students = await self._batch_query_existing_students(
            feishu_client, student_table, list(unique_students.keys())
        )
        
        # 构建现有学员映射
        existing_students_mapping = {}
        for student in existing_students:
            user_id = student["fields"].get("用户ID")
            if user_id:
                student_id_mapping[user_id] = student["record_id"]
                existing_students_mapping[user_id] = student
        
        self.process_logger.step(f"找到{len(existing_students)}个现有学员")
        
        # 处理每个学员
        for user_id, student_data in unique_students.items():
            try:
                if user_id in student_id_mapping:
                    # 现有学员，检查并更新字段
                    updated = await self._update_student_if_needed(
                        feishu_client, student_table, student_data, 
                        student_id_mapping[user_id], existing_students_mapping[user_id],
                        field_mapping_service, feishu_field_names, result
                    )
                    if updated:
                        result.updated_students += 1
                else:
                    # 新学员，创建记录
                    record_id = await self._create_new_student(
                        feishu_client, student_table, student_data, 
                        field_mapping_service, feishu_field_names, result
                    )
                    if record_id:
                        student_id_mapping[user_id] = record_id
                
                result.processed_records += 1
                
            except Exception as e:
                result.add_error(f"处理学员{user_id}失败: {str(e)}")
        
        # 设置字段映射摘要
        result.set_field_mapping_summary(field_mapping_service)
        
        return student_id_mapping
    
    async def _batch_query_existing_students(
        self,
        feishu_client: FeishuClient,
        student_table: TableConfig,
        user_ids: List[str]
    ) -> List[Dict]:
        """批量查询现有学员 - 使用缓存优化版本"""
        try:
            # 确保缓存已加载
            cache_loaded = await self.cache_manager.ensure_cache_loaded(
                feishu_client, student_table
            )

            if not cache_loaded:
                logger.warning("缓存加载失败，降级为直接查询")
                # 如果缓存加载失败，使用原始方法
                return await self._fallback_query_existing_students(
                    feishu_client, student_table, user_ids
                )

            # 从缓存批量获取学员信息
            cached_students = self.cache_manager.get_students_batch(user_ids)

            logger.info(
                f"从缓存查询学员: 请求 {len(user_ids)} 个，"
                f"找到 {len(cached_students)} 个"
            )

            # 获取缓存统计信息
            cache_stats = self.cache_manager.get_cache_stats()
            logger.info(
                f"缓存状态: 总记录 {cache_stats['total_records']}, "
                f"唯一用户 {cache_stats['unique_users']}, "
                f"缓存年龄 {cache_stats.get('age_hours', 0):.1f} 小时"
            )

            return cached_students

        except Exception as e:
            logger.error(f"使用缓存查询失败: {e}")
            # 如果缓存查询失败，降级为直接查询
            return await self._fallback_query_existing_students(
                feishu_client, student_table, user_ids
            )

    async def _fallback_query_existing_students(
        self,
        feishu_client: FeishuClient,
        student_table: TableConfig,
        user_ids: List[str]
    ) -> List[Dict]:
        """降级方案：直接查询现有学员"""
        all_students = []

        try:
            # 获取所有学员记录（分页处理）
            page_token = None
            while True:
                query_result = await feishu_client.query_records(
                    student_table.app_token,
                    student_table.table_id,
                    page_size=500,
                    page_token=page_token
                )

                records = query_result.get("records", [])
                all_students.extend(records)

                # 检查是否有更多数据
                if not query_result.get("has_more", False):
                    break
                page_token = query_result.get("page_token")

            # 客户端过滤：只保留匹配的用户ID
            filtered_students = []
            for record in all_students:
                record_user_id = record.get("fields", {}).get("用户ID")
                if record_user_id in user_ids:
                    filtered_students.append(record)

            return filtered_students

        except Exception as e:
            logger.warning(f"降级查询学员失败: {e}")
            return []
    
    async def _create_new_student(
        self, 
        feishu_client: FeishuClient, 
        student_table: TableConfig, 
        student_data: Dict[str, Any], 
        field_mapping_service: 'FieldMappingService',
        feishu_field_names: List[str],
        result: SyncResult
    ) -> Optional[str]:
        """创建新学员记录"""
        try:
            # 基本必要字段
            fields = {
                "用户ID": student_data["user_id"],
                "昵称": student_data["nickname"],
            }
            
            # 处理手机号字段，确保格式正确
            if student_data.get("phone"):
                phone_value = student_data["phone"]
                try:
                    # 去除手机号中的所有非数字字符（与更新逻辑保持一致）
                    phone_digits = ''.join(filter(str.isdigit, str(phone_value)))

                    # 如果没有数字，跳过
                    if not phone_digits:
                        logger.warning(f"手机号无有效数字，跳过: {phone_value}")
                    else:
                        # 验证手机号长度
                        if len(phone_digits) < 7 or len(phone_digits) > 15:
                            logger.warning(f"手机号长度异常: {phone_digits} (长度: {len(phone_digits)})")

                        # 保持为字符串格式，因为飞书中手机号字段是文本类型
                        fields["手机号"] = phone_digits

                except Exception as e:
                    logger.warning(f"手机号处理失败: {phone_value}, 错误: {e}")
                    # 如果处理失败，使用清理后的字符串
                    fields["手机号"] = str(phone_value).strip()
            
            # 添加CSV中的其他字段
            csv_all_fields = student_data.get('csv_all_fields', {})
            if csv_all_fields:
                additional_fields = field_mapping_service.map_csv_fields_to_feishu(
                    csv_all_fields, feishu_field_names
                )
                fields.update(additional_fields)
            
            record = await feishu_client.create_record(
                student_table.app_token,
                student_table.table_id,
                fields
            )

            # 更新缓存
            if self.cache_manager.is_loaded:
                self.cache_manager.add_student(
                    student_data["user_id"],
                    {
                        "record_id": record["record_id"],
                        "fields": fields
                    }
                )

            result.new_students += 1
            return record["record_id"]
            
        except Exception as e:
            result.add_error(f"创建学员{student_data['user_id']}失败: {str(e)}")
            return None
    
    async def _update_student_if_needed(
        self, 
        feishu_client: FeishuClient, 
        student_table: TableConfig, 
        student_data: Dict[str, Any], 
        record_id: str, 
        existing_student: Dict[str, Any],
        field_mapping_service: 'FieldMappingService',
        feishu_field_names: List[str],
        result: SyncResult
    ) -> bool:
        """如果需要则更新学员信息"""
        try:
            # 获取CSV中的所有字段
            csv_all_fields = student_data.get('csv_all_fields', {})
            if not csv_all_fields:
                return False
            
            # 映射CSV字段到飞书字段
            new_fields = field_mapping_service.map_csv_fields_to_feishu(
                csv_all_fields, feishu_field_names
            )
            
            if not new_fields:
                return False
            
            # 检测冲突
            conflicts = field_mapping_service.detect_conflicts(
                new_fields, existing_student, student_data["user_id"], student_data["nickname"]
            )
            
            # 分离无冲突的字段和有冲突的字段
            safe_updates = {}
            conflicted_fields = {c.field_name for c in conflicts}
            
            for field_name, new_value in new_fields.items():
                if field_name not in conflicted_fields:
                    # 检查是否为空字段（可以安全更新）
                    existing_value = existing_student.get("fields", {}).get(field_name)
                    if not existing_value or str(existing_value).strip() == "":
                        safe_updates[field_name] = new_value
            
            # 执行安全更新
            if safe_updates:
                try:
                    # 详细记录即将更新的字段
                    logger.info(f"准备更新学员 {student_data['user_id']} 字段: {safe_updates}")

                    # 验证数据格式
                    for field_name, field_value in safe_updates.items():
                        logger.debug(f"字段 {field_name}: 值='{field_value}', 类型={type(field_value)}")

                    await feishu_client.update_record(
                        student_table.app_token,
                        student_table.table_id,
                        record_id,
                        safe_updates
                    )

                    logger.info(f"成功更新学员 {student_data['user_id']} 字段")

                    # 更新缓存
                    if self.cache_manager.is_loaded:
                        # 获取当前缓存的记录并更新字段
                        cached_record = self.cache_manager.get_student(student_data["user_id"])
                        if cached_record:
                            cached_record["fields"].update(safe_updates)
                            self.cache_manager.update_student(
                                student_data["user_id"],
                                cached_record
                            )

                    # 记录更新信息
                    updated_info = ", ".join([f"{k}: {v}" for k, v in safe_updates.items()])
                    self.process_logger.step(f"更新学员 {student_data['user_id']} 字段: {updated_info}")

                    return True
                    
                except Exception as e:
                    error_msg = f"更新学员{student_data['user_id']}字段失败: {str(e)}"
                    logger.error(f"{error_msg} - 尝试更新的字段: {safe_updates}")

                    # 检查是否是NumberFieldConvFail错误
                    if "NumberFieldConvFail" in str(e):
                        # 分析哪个字段可能导致了问题
                        for field_name, field_value in safe_updates.items():
                            logger.error(f"疑似问题字段 {field_name}: 值='{field_value}', 类型={type(field_value)}")

                    result.add_error(error_msg)
                    return False
            
            # 如果有冲突，记录警告信息
            if conflicts:
                conflict_info = []
                for conflict in conflicts:
                    conflict_info.append(
                        f"{conflict.field_name}: 现有值'{conflict.existing_value}' vs 新值'{conflict.new_value}'"
                    )
                result.add_warning(
                    f"学员{student_data['nickname']}存在字段冲突，需要手动确认: {'; '.join(conflict_info)}"
                )
            
            return False
            
        except Exception as e:
            result.add_error(f"更新学员{student_data['user_id']}失败: {str(e)}")
            return False
    
    async def _sync_learning_records(
        self, 
        feishu_client: FeishuClient, 
        learning_records: List[Dict[str, Any]], 
        student_id_mapping: Dict[str, str], 
        result: SyncResult
    ):
        """同步学习记录"""
        self.process_logger.step(f"开始同步学习记录: {len(learning_records)}条记录")
        
        learning_table = self.config.learning_record_table
        
        for record in learning_records:
            try:
                user_id = record["user_id"]
                
                # 检查学员是否存在
                if user_id not in student_id_mapping:
                    result.add_warning(f"学员{user_id}不存在，跳过学习记录")
                    continue
                
                # 创建学习记录
                await self._create_learning_record(
                    feishu_client, learning_table, record, 
                    student_id_mapping[user_id], result
                )
                
            except Exception as e:
                result.add_error(f"处理学习记录失败: {str(e)}")
    
    async def _create_learning_record(
        self, 
        feishu_client: FeishuClient, 
        learning_table: TableConfig, 
        record_data: Dict[str, Any], 
        student_record_id: str, 
        result: SyncResult
    ):
        """创建学习记录"""
        try:
            fields = {
                "用户ID": record_data["user_id"],
                "昵称": record_data.get("nickname", ""),  # 添加昵称字段
                "课程": record_data["course"],
                "学习日期": format_date_field(record_data["learning_date"]),
                "学员总表": create_link_field(student_record_id)  # 修正关联字段名称
            }
            
            await feishu_client.create_record(
                learning_table.app_token,
                learning_table.table_id,
                fields
            )
            
            result.new_learning_records += 1
            
        except Exception as e:
            result.add_error(f"创建学习记录失败: {str(e)}")
    
    async def test_table_connection(self, table_config: TableConfig) -> Dict[str, Any]:
        """测试表格连接"""
        try:
            async with FeishuClient(self.config) as feishu_client:
                # 测试基本连接
                connection_test = await feishu_client.test_connection()
                if not connection_test["success"]:
                    return connection_test
                
                # 测试表格访问
                fields = await feishu_client.get_table_fields(
                    table_config.app_token,
                    table_config.table_id
                )
                
                return {
                    "success": True,
                    "message": "表格连接成功",
                    "data": {
                        "table_name": table_config.name,
                        "field_count": len(fields),
                        "fields": [{"name": f["field_name"], "type": f["type"]} for f in fields]
                    }
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"表格连接失败: {str(e)}"
            }

    async def get_table_fields_info(self) -> Dict[str, Any]:
        """获取表格字段信息（用于字段映射配置）"""
        try:
            async with FeishuClient(self.config) as feishu_client:
                # 获取学员总表字段
                student_fields = await feishu_client.get_table_fields(
                    self.config.student_table.app_token,
                    self.config.student_table.table_id
                )

                # 获取学习记录表字段
                learning_fields = await feishu_client.get_table_fields(
                    self.config.learning_record_table.app_token,
                    self.config.learning_record_table.table_id
                )

                # 格式化字段信息
                def format_fields(fields):
                    return [
                        {
                            "field_name": f["field_name"],
                            "field_id": f["field_id"],
                            "type": f["type"],
                            "type_name": self._get_field_type_name(f["type"]),
                            "property": f.get("property", {})
                        }
                        for f in fields
                    ]

                return {
                    "success": True,
                    "data": {
                        "student_table": {
                            "fields": format_fields(student_fields),
                            "field_count": len(student_fields)
                        },
                        "learning_record_table": {
                            "fields": format_fields(learning_fields),
                            "field_count": len(learning_fields)
                        }
                    }
                }

        except Exception as e:
            logger.error(f"获取表格字段信息失败: {e}")
            return {
                "success": False,
                "message": f"获取表格字段信息失败: {str(e)}"
            }

    def _get_field_type_name(self, field_type: int) -> str:
        """获取字段类型名称"""
        type_mapping = {
            1: "多行文本",
            2: "数字",
            3: "单选",
            4: "多选",
            5: "日期",
            7: "复选框",
            11: "人员",
            13: "电话号码",
            15: "超链接",
            17: "附件",
            1001: "关联记录",
            1005: "单行文本"
        }
        return type_mapping.get(field_type, f"未知类型({field_type})")
    
    async def validate_table_structure(self) -> Dict[str, Any]:
        """验证表格结构"""
        try:
            async with FeishuClient(self.config) as feishu_client:
                # 验证学员总表
                student_result = await self.test_table_connection(self.config.student_table)
                
                # 验证学习记录表
                learning_result = await self.test_table_connection(self.config.learning_record_table)
                
                success = student_result["success"] and learning_result["success"]
                
                return {
                    "success": success,
                    "message": "表格结构验证完成",
                    "data": {
                        "student_table": student_result,
                        "learning_record_table": learning_result
                    }
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"表格结构验证失败: {str(e)}"
            }

    async def update_selected_conflicts(self, selected_conflicts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """更新选中的冲突字段"""
        try:
            self.process_logger.start(f"开始更新{len(selected_conflicts)}个冲突字段")
            
            updated_count = 0
            failed_count = 0
            errors = []
            
            async with FeishuClient(self.config) as feishu_client:
                # 测试连接
                connection_test = await feishu_client.test_connection()
                if not connection_test["success"]:
                    return {
                        "success": False,
                        "message": f"飞书连接失败: {connection_test['message']}"
                    }
                
                student_table = self.config.student_table
                
                # 按用户ID分组冲突
                user_conflicts = {}
                for conflict in selected_conflicts:
                    user_id = conflict["user_id"]
                    if user_id not in user_conflicts:
                        user_conflicts[user_id] = []
                    user_conflicts[user_id].append(conflict)
                
                # 对每个用户更新冲突字段
                for user_id, conflicts in user_conflicts.items():
                    try:
                        # 查找用户的记录ID
                        user_record = await self._find_user_record(feishu_client, student_table, user_id)
                        if not user_record:
                            errors.append(f"用户{user_id}不存在")
                            failed_count += len(conflicts)
                            continue
                        
                        # 准备更新字段
                        update_fields = {}
                        for conflict in conflicts:
                            field_name = conflict["field_name"]
                            new_value = conflict["new_value"]
                            update_fields[field_name] = new_value
                        
                        # 执行更新
                        await feishu_client.update_record(
                            student_table.app_token,
                            student_table.table_id,
                            user_record["record_id"],
                            update_fields
                        )
                        
                        updated_count += len(conflicts)
                        self.process_logger.step(f"用户{user_id}更新{len(conflicts)}个字段成功")
                        
                    except Exception as e:
                        error_msg = f"用户{user_id}更新失败: {str(e)}"
                        errors.append(error_msg)
                        failed_count += len(conflicts)
                        logger.error(error_msg)
            
            self.process_logger.finish(f"冲突更新完成: 成功{updated_count}个，失败{failed_count}个")
            
            return {
                "success": True,
                "message": f"冲突更新完成: 成功{updated_count}个，失败{failed_count}个",
                "data": {
                    "updated_count": updated_count,
                    "failed_count": failed_count,
                    "errors": errors
                }
            }
            
        except Exception as e:
            error_msg = f"冲突更新过程发生异常: {str(e)}"
            self.process_logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg
            }

    async def _find_user_record(self, feishu_client: FeishuClient, student_table: TableConfig, user_id: str) -> Optional[Dict]:
        """查找用户记录"""
        try:
            # 使用客户端过滤方式查找用户记录
            page_token = None
            while True:
                query_result = await feishu_client.query_records(
                    student_table.app_token,
                    student_table.table_id,
                    page_size=500,
                    page_token=page_token
                )
                
                records = query_result.get("records", [])
                
                # 查找匹配的用户ID
                for record in records:
                    record_user_id = record.get("fields", {}).get("用户ID")
                    if record_user_id == user_id:
                        return record
                
                # 检查是否有更多数据
                if not query_result.get("has_more", False):
                    break
                page_token = query_result.get("page_token")
            
            return None
            
        except Exception as e:
            logger.error(f"查找用户记录失败: {e}")
            return None

# 工具函数
def create_sync_service(config: AppConfig) -> StudentSyncService:
    """创建同步服务实例"""
    return StudentSyncService(config)

async def quick_sync(
    config: AppConfig, 
    file_content: bytes, 
    filename: str,
    course_name: str = None,
    learning_date: str = None
) -> Dict[str, Any]:
    """快速同步接口"""
    service = StudentSyncService(config)
    return await service.sync_csv_data(
        file_content, 
        filename, 
        course_name=course_name, 
        learning_date=learning_date
    ) 