"""
字段映射记忆管理器
用于保存和加载用户的字段映射配置历史
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class MappingMemory:
    """映射配置记忆管理器"""

    def __init__(self, config_file: str = "config/field_mappings_history.json"):
        self.config_file = config_file
        self.ensure_config_dir()
        self.history = self.load_history()

    def ensure_config_dir(self):
        """确保配置目录存在"""
        config_dir = os.path.dirname(self.config_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

    def load_history(self) -> Dict[str, Any]:
        """加载历史映射配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    logger.info(f"加载映射历史成功: {self.config_file}")
                    return history
            else:
                logger.info("映射历史文件不存在，创建新的历史记录")
                return self._create_empty_history()
        except Exception as e:
            logger.error(f"加载映射历史失败: {e}")
            return self._create_empty_history()

    def _create_empty_history(self) -> Dict[str, Any]:
        """创建空的历史记录结构"""
        return {
            "last_mapping": None,
            "mapping_history": [],
            "created_at": datetime.now().isoformat(),
            "version": "1.0"
        }

    def get_last_mapping_for_csv(self, csv_headers: List[str]) -> Optional[Dict[str, Any]]:
        """
        获取适用于当前CSV的上次映射配置

        Args:
            csv_headers: CSV文件的字段列表

        Returns:
            映射配置字典，如果没有匹配的历史记录则返回None
            格式：{
                "regular_mappings": {csv_field: feishu_field},
                "note_mappings": [csv_field1, csv_field2]
            }
        """
        if not self.history.get("last_mapping"):
            logger.info("没有找到历史映射配置")
            return None

        last = self.history["last_mapping"]
        last_headers = last.get("csv_headers", [])
        last_mapping = last.get("mapping", {})

        # 检查是否为新格式
        if isinstance(last_mapping, dict) and "regular_mappings" in last_mapping:
            # 新格式处理
            regular_mappings = last_mapping.get("regular_mappings", {})
            note_mappings = last_mapping.get("note_mappings", [])

            # 检查CSV字段是否完全匹配
            if set(csv_headers) == set(last_headers):
                logger.info("找到完全匹配的历史映射配置（新格式）")
                return last_mapping

            # 部分匹配处理
            partial_regular = {}
            partial_note = []

            for csv_field in csv_headers:
                if csv_field in regular_mappings:
                    partial_regular[csv_field] = regular_mappings[csv_field]
                if csv_field in note_mappings:
                    partial_note.append(csv_field)

            if partial_regular or partial_note:
                result = {
                    "regular_mappings": partial_regular,
                    "note_mappings": partial_note
                }
                logger.info(f"找到部分匹配的历史映射配置（新格式）: {len(partial_regular)} 常规字段, {len(partial_note)} 备注字段")
                return result

        else:
            # 兼容旧格式
            # 检查CSV字段是否完全匹配
            if set(csv_headers) == set(last_headers):
                logger.info("找到完全匹配的历史映射配置（旧格式）")
                return {
                    "regular_mappings": last_mapping,
                    "note_mappings": []
                }

            # 检查是否有部分匹配的字段
            partial_mapping = {}
            for csv_field in csv_headers:
                if csv_field in last_mapping:
                    partial_mapping[csv_field] = last_mapping[csv_field]

            if partial_mapping:
                logger.info(f"找到部分匹配的历史映射配置（旧格式）: {len(partial_mapping)}/{len(csv_headers)} 个字段")
                return {
                    "regular_mappings": partial_mapping,
                    "note_mappings": []
                }

        logger.info("没有找到匹配的历史映射配置")
        return None

    def save_mapping(self, csv_headers: List[str], mapping: Dict[str, Any]) -> bool:
        """
        保存本次映射配置

        Args:
            csv_headers: CSV文件的字段列表
            mapping: 映射配置，支持新旧格式
                    新格式：{"regular_mappings": {csv_field: feishu_field}, "note_mappings": [csv_field]}
                    旧格式：{csv_field: feishu_field}

        Returns:
            保存是否成功
        """
        try:
            # 标准化映射格式
            if isinstance(mapping, dict) and "regular_mappings" in mapping:
                # 新格式
                normalized_mapping = mapping
                regular_count = len(mapping.get("regular_mappings", {}))
                note_count = len(mapping.get("note_mappings", []))
                total_mapped = regular_count + note_count
            else:
                # 旧格式，转换为新格式
                normalized_mapping = {
                    "regular_mappings": mapping,
                    "note_mappings": []
                }
                total_mapped = len(mapping)

            # 更新最近使用的映射
            self.history["last_mapping"] = {
                "csv_headers": csv_headers,
                "mapping": normalized_mapping,
                "timestamp": datetime.now().isoformat(),
                "field_count": len(csv_headers),
                "mapped_count": total_mapped
            }

            # 添加到历史记录
            history_entry = {
                "name": f"映射_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "csv_headers": csv_headers,
                "mapping": normalized_mapping,
                "timestamp": datetime.now().isoformat(),
                "field_count": len(csv_headers),
                "mapped_count": total_mapped
            }

            # 保持历史记录不超过10条
            self.history["mapping_history"].append(history_entry)
            if len(self.history["mapping_history"]) > 10:
                self.history["mapping_history"] = self.history["mapping_history"][-10:]

            # 保存到文件
            return self._save_to_file()

        except Exception as e:
            logger.error(f"保存映射配置失败: {e}")
            return False

    def _save_to_file(self) -> bool:
        """将历史记录保存到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            logger.info(f"映射历史保存成功: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存映射历史文件失败: {e}")
            return False

    def get_mapping_history(self) -> List[Dict[str, Any]]:
        """获取映射历史记录"""
        return self.history.get("mapping_history", [])

    def clear_history(self) -> bool:
        """清除所有历史记录"""
        try:
            self.history = self._create_empty_history()
            return self._save_to_file()
        except Exception as e:
            logger.error(f"清除历史记录失败: {e}")
            return False

    def get_mapping_statistics(self) -> Dict[str, Any]:
        """获取映射使用统计"""
        history = self.history.get("mapping_history", [])

        if not history:
            return {
                "total_mappings": 0,
                "most_common_fields": [],
                "last_used": None
            }

        # 统计最常用的字段映射
        field_usage = {}
        for entry in history:
            mapping = entry.get("mapping", {})

            # 处理新格式
            if isinstance(mapping, dict) and "regular_mappings" in mapping:
                # 统计常规映射
                for csv_field, feishu_field in mapping.get("regular_mappings", {}).items():
                    key = f"{csv_field} → {feishu_field}"
                    field_usage[key] = field_usage.get(key, 0) + 1

                # 统计备注映射
                for csv_field in mapping.get("note_mappings", []):
                    key = f"{csv_field} → 备注"
                    field_usage[key] = field_usage.get(key, 0) + 1
            else:
                # 兼容旧格式
                for csv_field, feishu_field in mapping.items():
                    key = f"{csv_field} → {feishu_field}"
                    field_usage[key] = field_usage.get(key, 0) + 1

        # 按使用频率排序
        most_common = sorted(field_usage.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_mappings": len(history),
            "most_common_fields": [{"mapping": k, "count": v} for k, v in most_common],
            "last_used": history[-1].get("timestamp") if history else None
        }