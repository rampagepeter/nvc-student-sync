#!/usr/bin/env python
"""测试冲突更新性能优化效果"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

async def test_performance_optimization():
    """测试性能优化"""

    base_url = "http://localhost:8000"

    print("=" * 60)
    print("冲突更新性能优化测试")
    print("=" * 60)
    print("\n优化内容:")
    print("1. FieldConflict 类现在包含 record_id")
    print("2. 更新时优先使用 record_id，避免查询")
    print("3. 使用缓存快速查找用户记录")
    print("=" * 60)

    # 模拟冲突数据（包含record_id的新格式）
    test_conflicts = [
        {
            "user_id": "TEST_USER_1",
            "nickname": "测试用户1",
            "field_name": "姓名",
            "existing_value": "旧姓名1",
            "new_value": "新姓名1",
            "record_id": "rec_123456"  # 新增：包含record_id
        },
        {
            "user_id": "TEST_USER_2",
            "nickname": "测试用户2",
            "field_name": "年龄",
            "existing_value": "25",
            "new_value": "26",
            "record_id": "rec_234567"  # 新增：包含record_id
        }
    ]

    async with aiohttp.ClientSession() as session:
        try:
            print("\n测试说明:")
            print("- 新的冲突数据包含 record_id")
            print("- 更新时应直接使用 record_id，无需查询")
            print("- 预期：毫秒级响应（之前需要30-60秒/用户）")

            print("\n模拟的冲突数据:")
            for conflict in test_conflicts:
                print(f"  用户: {conflict['user_id']}, 字段: {conflict['field_name']}, record_id: {conflict['record_id']}")

            # 记录开始时间
            start_time = time.time()

            print("\n执行冲突更新...")
            async with session.post(
                f"{base_url}/api/conflicts/update",
                json={"selected_conflicts": test_conflicts},
                headers={'Content-Type': 'application/json'}
            ) as resp:
                result = await resp.json()

                # 记录结束时间
                end_time = time.time()
                elapsed_time = end_time - start_time

                print(f"\n更新结果:")
                print(f"  状态: {'✅ 成功' if result.get('success') else '❌ 失败'}")
                print(f"  消息: {result.get('message')}")
                print(f"  ⏱️  耗时: {elapsed_time:.2f} 秒")

                if result.get('data'):
                    data = result['data']
                    print(f"\n统计:")
                    print(f"  成功更新: {data.get('updated_count', 0)} 个")
                    print(f"  失败: {data.get('failed_count', 0)} 个")

                    if data.get('errors'):
                        print(f"\n错误信息:")
                        for error in data['errors']:
                            print(f"  - {error}")

            print("\n" + "=" * 60)
            print("性能对比:")
            print(f"  优化前: ~30-60秒/用户")
            print(f"  优化后: {elapsed_time:.2f} 秒/2用户")
            print(f"  性能提升: 显著" if elapsed_time < 5 else "需要进一步优化")

            print("\n注意:")
            print("- 这是模拟测试，实际用户可能不存在")
            print("- 重点是验证代码逻辑和性能改进")
            print("- 实际使用时，冲突数据会自动包含正确的record_id")

        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

async def check_cache_status():
    """检查缓存状态"""
    base_url = "http://localhost:8000"

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base_url}/api/cache/status") as resp:
            result = await resp.json()
            if result.get('success'):
                data = result.get('data', {})
                print("\n缓存状态:")
                print(f"  缓存存在: {data.get('cache_exists', False)}")
                print(f"  记录数: {data.get('total_records', 0)}")
                print(f"  最后更新: {data.get('last_update', 'N/A')}")
                print(f"  缓存年龄: {data.get('age_hours', 'N/A')} 小时")

if __name__ == "__main__":
    print("开始性能优化测试...\n")

    # 先检查缓存状态
    asyncio.run(check_cache_status())

    # 执行性能测试
    asyncio.run(test_performance_optimization())