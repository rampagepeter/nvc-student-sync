#!/usr/bin/env python3
"""
测试重复数据问题修复
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_duplicate_fix():
    """测试重复数据问题修复"""
    print("🔧 测试重复数据问题修复...")
    
    # 等待服务器启动
    print("等待服务器启动...")
    time.sleep(8)
    
    # 创建测试CSV内容 - 使用已存在的用户ID
    csv_content = """用户ID,昵称,手机号
u_68673b8a1c903_zPAQOhvYHc,重复测试用户1,13800138000
u_6867340e15746_RuuT0fwiYU,重复测试用户2,13800138001
duplicate_test_001,新用户测试1,13800138002"""
    
    print("\n📤 上传重复测试数据")
    files = {
        'file': ('duplicate_test.csv', csv_content.encode('utf-8'), 'text/csv')
    }
    data = {
        'courseName': '重复测试课程',
        'learningDate': '2025-03-06'
    }
    
    try:
        # 上传文件
        response = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
        print(f"上传状态码: {response.status_code}")
        upload_result = response.json()
        
        if not upload_result.get('success'):
            print(f"❌ 上传失败: {upload_result.get('message')}")
            return
        
        print(f"✅ 上传成功: {upload_result.get('message')}")
        
        # 开始同步
        print("\n🔄 开始同步处理")
        sync_response = requests.post(f"{BASE_URL}/api/sync")
        print(f"同步状态码: {sync_response.status_code}")
        sync_result = sync_response.json()
        
        if sync_result.get('success'):
            print(f"✅ 同步成功!")
            
            # 显示同步结果
            data = sync_result.get('data', {})
            print(f"📊 同步结果:")
            print(f"  - 新增学员: {data.get('new_students', 0)}")
            print(f"  - 新增学习记录: {data.get('new_learning_records', 0)}")
            print(f"  - 处理记录总数: {data.get('processed_records', 0)}")
            print(f"  - 错误数量: {len(data.get('errors', []))}")
            
            if data.get('errors'):
                print(f"❌ 错误信息:")
                for error in data.get('errors', []):
                    print(f"  - {error}")
                    
        else:
            print(f"❌ 同步失败: {sync_result.get('message')}")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")

if __name__ == "__main__":
    test_duplicate_fix() 