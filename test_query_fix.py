#!/usr/bin/env python3
"""
测试修复后的查询功能
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_query_fix():
    """测试查询功能修复"""
    print("🔍 测试修复后的查询功能...")
    
    # 等待服务器启动
    print("等待服务器启动...")
    time.sleep(5)
    
    # 创建测试CSV内容
    csv_content = """用户ID,昵称,手机号
query_test_001,查询测试用户1,13800138000
query_test_002,查询测试用户2,13800138001
query_test_003,查询测试用户3,13800138002"""
    
    print("\n📤 步骤1: 上传测试数据")
    files = {
        'file': ('query_test.csv', csv_content.encode('utf-8'), 'text/csv')
    }
    data = {
        'courseName': '查询测试课程',
        'learningDate': '2025-03-06'
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
        print(f"上传状态码: {response.status_code}")
        upload_result = response.json()
        print(f"上传结果: {json.dumps(upload_result, indent=2, ensure_ascii=False)}")
        
        if not upload_result.get('success'):
            print(f"❌ 上传失败: {upload_result.get('message')}")
            return
        
        print("\n🔄 步骤2: 开始同步")
        sync_response = requests.post(f"{BASE_URL}/api/sync")
        print(f"同步状态码: {sync_response.status_code}")
        sync_result = sync_response.json()
        print(f"同步结果: {json.dumps(sync_result, indent=2, ensure_ascii=False)}")
        
        if sync_result.get('success'):
            print("✅ 第一次同步成功!")
            
            # 等待一会儿，然后再次上传相同数据测试去重功能
            print("\n⏳ 等待3秒后测试去重功能...")
            time.sleep(3)
            
            print("\n📤 步骤3: 再次上传相同数据测试去重")
            response2 = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
            upload_result2 = response2.json()
            print(f"第二次上传结果: {json.dumps(upload_result2, indent=2, ensure_ascii=False)}")
            
            if upload_result2.get('success'):
                sync_response2 = requests.post(f"{BASE_URL}/api/sync")
                sync_result2 = sync_response2.json()
                print(f"第二次同步结果: {json.dumps(sync_result2, indent=2, ensure_ascii=False)}")
                
                if sync_result2.get('success'):
                    # 检查是否正确识别了现有学员
                    data2 = sync_result2.get('data', {})
                    new_students2 = data2.get('new_students', 0)
                    
                    if new_students2 == 0:
                        print("✅ 去重功能正常！第二次同步没有创建新学员")
                    else:
                        print(f"⚠️ 去重功能可能有问题，第二次同步创建了 {new_students2} 个新学员")
                else:
                    print(f"❌ 第二次同步失败: {sync_result2.get('message')}")
        else:
            print(f"❌ 第一次同步失败: {sync_result.get('message')}")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    test_query_fix() 