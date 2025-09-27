"""
学员缓存管理器
用于缓存飞书学员总表数据，提高查询性能
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import pickle

logger = logging.getLogger(__name__)


class StudentCacheManager:
    """学员缓存管理器"""

    def __init__(self, cache_dir: str = "cache", ttl_hours: int = 24):
        """
        初始化缓存管理器

        Args:
            cache_dir: 缓存目录
            ttl_hours: 缓存有效期（小时）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "students_cache.pkl"
        self.meta_file = self.cache_dir / "cache_meta.json"
        self.ttl_hours = ttl_hours

        # 内存缓存
        self.cache: Dict[str, Dict] = {}  # user_id -> record 映射
        self.is_loaded = False
        self.last_update: Optional[datetime] = None
        self.total_records = 0

        # 创建缓存目录
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        if not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"创建缓存目录: {self.cache_dir}")

            # 创建.gitignore文件
            gitignore_file = self.cache_dir / ".gitignore"
            gitignore_file.write_text("*\n!.gitignore\n")

    async def load_all_students(self, feishu_client, table_config) -> bool:
        """
        从飞书加载所有学员数据到缓存

        Args:
            feishu_client: 飞书客户端
            table_config: 表格配置

        Returns:
            是否加载成功
        """
        try:
            logger.info("开始加载学员数据到缓存...")
            start_time = datetime.now()

            all_students = []
            page_token = None
            page_count = 0

            # 分页获取所有记录
            while True:
                query_result = await feishu_client.query_records(
                    table_config.app_token,
                    table_config.table_id,
                    page_size=500,
                    page_token=page_token
                )

                records = query_result.get("records", [])
                all_students.extend(records)
                page_count += 1

                # 每10页记录一次进度
                if page_count % 10 == 0:
                    logger.info(f"缓存加载进度: 已加载 {len(all_students)} 条记录...")

                # 检查是否有更多数据
                if not query_result.get("has_more", False):
                    break

                page_token = query_result.get("page_token")
                if not page_token:
                    break

            # 构建缓存映射
            self.cache.clear()
            for record in all_students:
                user_id = record.get("fields", {}).get("用户ID")
                if user_id:
                    self.cache[user_id] = record

            # 更新元数据
            self.is_loaded = True
            self.last_update = datetime.now()
            self.total_records = len(all_students)

            # 保存到文件
            await self._save_to_file()

            elapsed_time = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"缓存加载完成: {self.total_records} 条记录, "
                f"{len(self.cache)} 个唯一用户, 耗时 {elapsed_time:.2f} 秒"
            )

            return True

        except Exception as e:
            logger.error(f"加载学员缓存失败: {e}")
            return False

    async def load_from_file(self) -> bool:
        """
        从文件加载缓存

        Returns:
            是否加载成功
        """
        try:
            # 检查缓存文件是否存在
            if not self.cache_file.exists() or not self.meta_file.exists():
                logger.info("缓存文件不存在")
                return False

            # 读取元数据
            with open(self.meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            # 不再检查过期，直接加载缓存数据
            last_update = datetime.fromisoformat(meta['last_update'])

            # 加载缓存数据
            with open(self.cache_file, 'rb') as f:
                self.cache = pickle.load(f)

            # 更新元数据
            self.is_loaded = True
            self.last_update = last_update
            self.total_records = meta['total_records']

            logger.info(
                f"从文件加载缓存成功: {self.total_records} 条记录, "
                f"{len(self.cache)} 个唯一用户"
            )

            return True

        except Exception as e:
            logger.error(f"从文件加载缓存失败: {e}")
            return False

    async def _save_to_file(self):
        """保存缓存到文件"""
        try:
            # 保存缓存数据
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)

            # 保存元数据
            meta = {
                'last_update': self.last_update.isoformat(),
                'total_records': self.total_records,
                'unique_users': len(self.cache)
            }

            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            logger.info("缓存已保存到文件")

        except Exception as e:
            logger.error(f"保存缓存到文件失败: {e}")

    def get_student(self, user_id: str) -> Optional[Dict]:
        """
        从缓存获取学员信息

        Args:
            user_id: 用户ID

        Returns:
            学员记录或None
        """
        return self.cache.get(user_id)

    def get_students_batch(self, user_ids: List[str]) -> List[Dict]:
        """
        批量获取学员信息

        Args:
            user_ids: 用户ID列表

        Returns:
            找到的学员记录列表
        """
        result = []
        for user_id in user_ids:
            student = self.cache.get(user_id)
            if student:
                result.append(student)
        return result

    def update_student(self, user_id: str, record: Dict):
        """
        更新缓存中的学员信息

        Args:
            user_id: 用户ID
            record: 学员记录
        """
        self.cache[user_id] = record
        self.last_update = datetime.now()
        logger.debug(f"更新缓存: 用户 {user_id}")

    def add_student(self, user_id: str, record: Dict):
        """
        添加新学员到缓存

        Args:
            user_id: 用户ID
            record: 学员记录
        """
        self.cache[user_id] = record
        self.total_records += 1
        self.last_update = datetime.now()
        logger.debug(f"添加到缓存: 新用户 {user_id}")

    async def save_cache_updates(self):
        """
        保存缓存更新到文件
        """
        if self.is_loaded:
            await self._save_to_file()
            logger.info("缓存更新已保存到文件")

    def is_cache_valid(self) -> bool:
        """
        检查缓存是否有效

        Returns:
            缓存是否已加载
        """
        # 只检查缓存是否已加载，不再检查过期时间
        return self.is_loaded

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            缓存统计信息
        """
        age = None
        if self.last_update:
            age = (datetime.now() - self.last_update).total_seconds() / 3600

        return {
            'is_loaded': self.is_loaded,
            'total_records': self.total_records,
            'unique_users': len(self.cache),
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'age_hours': round(age, 2) if age else None,
            'is_valid': self.is_cache_valid()  # 现在只表示是否已加载
        }

    async def ensure_cache_loaded(self, feishu_client, table_config) -> bool:
        """
        确保缓存已加载（优先从文件，其次从API）

        Args:
            feishu_client: 飞书客户端
            table_config: 表格配置

        Returns:
            是否成功加载
        """
        # 如果缓存已经有效，直接返回
        if self.is_cache_valid():
            return True

        # 尝试从文件加载
        if await self.load_from_file():
            return True

        # 从API加载
        return await self.load_all_students(feishu_client, table_config)

    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.is_loaded = False
        self.last_update = None
        self.total_records = 0

        # 删除缓存文件
        if self.cache_file.exists():
            self.cache_file.unlink()
        if self.meta_file.exists():
            self.meta_file.unlink()

        logger.info("缓存已清空")