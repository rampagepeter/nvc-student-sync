#!/usr/bin/env python
"""改进的备注字段空内容测试"""

import sys
sys.path.append('backend')

from backend.sync_service import FieldMappingService

def test_note_content_generation():
    """直接测试备注内容生成逻辑"""

    print("=" * 60)
    print("测试备注内容生成逻辑")
    print("=" * 60)

    # 创建字段映射服务
    service = FieldMappingService()

    # 设置备注映射字段
    service.note_mappings = ["地址", "行业", "其他信息"]

    # 测试场景1：所有字段都为空
    print("\n测试1: 所有备注字段为空")
    csv_fields_empty = {
        "用户ID": "TEST001",
        "昵称": "测试用户",
        "地址": "",
        "行业": None,
        "其他信息": "   "  # 只有空格
    }
    result = service._build_note_content(csv_fields_empty, "测试课程", "2025-09-30")
    if result:
        print(f"  ❌ 错误：生成了内容\n{result}")
    else:
        print(f"  ✅ 正确：返回空字符串（不生成内容）")

    # 测试场景2：部分字段有值
    print("\n测试2: 部分备注字段有值")
    csv_fields_partial = {
        "用户ID": "TEST002",
        "昵称": "测试用户2",
        "地址": "",
        "行业": "互联网",
        "其他信息": None
    }
    result = service._build_note_content(csv_fields_partial, "测试课程", "2025-09-30")
    if result:
        print(f"  ✅ 正确：生成了内容")
        print(f"  生成的内容：\n{result}")
    else:
        print(f"  ❌ 错误：没有生成内容")

    # 测试场景3：所有字段都有值
    print("\n测试3: 所有备注字段都有值")
    csv_fields_full = {
        "用户ID": "TEST003",
        "昵称": "测试用户3",
        "地址": "北京市朝阳区",
        "行业": "金融",
        "其他信息": "VIP客户"
    }
    result = service._build_note_content(csv_fields_full, "测试课程", "2025-09-30")
    if result:
        print(f"  ✅ 正确：生成了内容")
        print(f"  生成的内容：\n{result}")
    else:
        print(f"  ❌ 错误：没有生成内容")

    # 测试场景4：包含特殊空值（nan, null等）
    print("\n测试4: 字段包含特殊空值")
    csv_fields_special = {
        "用户ID": "TEST004",
        "昵称": "测试用户4",
        "地址": "nan",
        "行业": "null",
        "其他信息": "None"
    }
    result = service._build_note_content(csv_fields_special, "测试课程", "2025-09-30")
    if result:
        print(f"  ❌ 错误：生成了内容（特殊空值应被忽略）\n{result}")
    else:
        print(f"  ✅ 正确：返回空字符串（特殊空值被正确识别）")

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print("\n改进后的 _build_note_content 方法：")
    print("✅ 1. 预先检查所有映射字段是否都为空")
    print("✅ 2. 识别并忽略特殊空值（nan, null, none等）")
    print("✅ 3. 只有至少一个字段有实际内容时才生成备注")
    print("✅ 4. 避免生成只有标题没有内容的空备注")

if __name__ == "__main__":
    test_note_content_generation()