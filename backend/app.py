from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入自定义模块
from backend.config import config_manager
from backend.utils import setup_logging, create_response, app_logger
from backend.sync_service import StudentSyncService
from backend.csv_processor import validate_csv_file

# 设置日志系统
setup_logging()

# 创建FastAPI应用实例
app = FastAPI(
    title="NVC学员信息同步工具",
    description="自动化处理从小鹅通导出的学员数据并同步到飞书多维表格",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# 全局变量存储上传的文件数据
uploaded_file_data = None

# 应用启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    try:
        app_logger.info("应用启动中...")
        
        # 尝试加载配置
        try:
            config_manager.load_config()
            app_logger.info("配置加载完成")
        except Exception as e:
            app_logger.warning(f"配置加载失败，将使用默认配置: {e}")
        
        app_logger.info("应用启动完成")
    except Exception as e:
        app_logger.error(f"应用启动失败: {e}")
        raise

# 应用关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    app_logger.info("应用关闭中...")

# 根路径 - 返回前端页面
@app.get("/", response_class=HTMLResponse)
async def root():
    """返回主页面"""
    frontend_file = frontend_dir / "index.html"
    if frontend_file.exists():
        return FileResponse(str(frontend_file))
    else:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>NVC学员信息同步工具</title>
            <meta charset="utf-8">
        </head>
        <body>
            <h1>NVC学员信息同步工具</h1>
            <p>前端页面未找到，请检查文件路径。</p>
        </body>
        </html>
        """)

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return create_response(
        success=True,
        message="服务正常运行",
        data={"status": "healthy"}
    )

# 配置相关接口
@app.get("/api/config")
async def get_config():
    """获取当前配置信息（脱敏）"""
    try:
        if config_manager.config:
            # 返回脱敏的配置信息
            config_dict = config_manager.config.dict()
            # 脱敏处理
            config_dict['feishu_app_id'] = "***" if config_dict['feishu_app_id'] else ""
            config_dict['feishu_app_secret'] = "***" if config_dict['feishu_app_secret'] else ""
            
            return create_response(
                success=True,
                message="配置信息获取成功",
                data=config_dict
            )
        else:
            return create_response(
                success=False,
                message="配置未加载"
            )
    except Exception as e:
        app_logger.error(f"获取配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/validate")
async def validate_config():
    """验证当前配置"""
    try:
        if not config_manager.config:
            return create_response(
                success=False,
                message="配置未加载"
            )
        
        validation_result = config_manager.validate_config(config_manager.config)
        
        return create_response(
            success=validation_result["valid"],
            message="配置验证完成",
            data=validation_result
        )
    except Exception as e:
        app_logger.error(f"配置验证失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/test-connection")
async def test_feishu_connection():
    """测试飞书连接"""
    try:
        if not config_manager.config:
            return create_response(
                success=False,
                message="配置未加载"
            )
        
        sync_service = StudentSyncService(config_manager.config)
        result = await sync_service.validate_table_structure()
        
        return create_response(
            success=result["success"],
            message=result["message"],
            data=result.get("data")
        )
        
    except Exception as e:
        app_logger.error(f"连接测试失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 文件上传接口
@app.post("/api/upload")
async def upload_csv(
    file: UploadFile = File(...),
    courseName: str = Form(...),
    learningDate: str = Form(...)
):
    """上传CSV文件"""
    global uploaded_file_data
    
    try:
        # 主动清除旧的缓存数据
        if uploaded_file_data:
            old_filename = uploaded_file_data.get("filename", "未知文件")
            app_logger.info(f"清除旧缓存文件: {old_filename}")
            uploaded_file_data = None
        else:
            app_logger.info("无需清除缓存，当前无已上传文件")
        
        app_logger.info(f"接收到上传请求 - 课程: '{courseName}', 日期: '{learningDate}', 文件: {file.filename}")
        
        # 验证必需参数
        if not courseName or not courseName.strip():
            app_logger.warning(f"课程名称为空: '{courseName}'")
            return create_response(
                success=False,
                message="请输入课程名称"
            )
        
        if not learningDate or not learningDate.strip():
            app_logger.warning(f"学习日期为空: '{learningDate}'")
            return create_response(
                success=False,
                message="请选择学习日期"
            )
        
        # 验证文件类型
        if not file.filename or not file.filename.endswith('.csv'):
            app_logger.warning(f"文件类型错误: {file.filename}")
            return create_response(
                success=False,
                message="请上传CSV格式的文件"
            )
        
        # 读取文件内容
        content = await file.read()
        file_size = len(content)
        
        # 验证文件大小（限制为10MB）
        if file_size > 10 * 1024 * 1024:  # 10MB
            app_logger.warning(f"文件大小超限: {file_size} bytes")
            return create_response(
                success=False,
                message="文件大小超过10MB限制"
            )
        
        app_logger.info(f"文件验证通过 - 文件: {file.filename}, 大小: {file_size} bytes, 课程: {courseName}, 日期: {learningDate}")
        
        # 验证CSV文件格式
        csv_validation = validate_csv_file(content, file.filename)
        if not csv_validation["valid"]:
            app_logger.error(f"CSV格式验证失败: {csv_validation['error']}")
            return create_response(
                success=False,
                message=f"CSV文件格式错误: {csv_validation['error']}"
            )
        
        # 存储文件数据到内存
        uploaded_file_data = {
            "content": content,
            "filename": file.filename,
            "size": file_size,
            "headers": csv_validation["headers"],
            "encoding": csv_validation["encoding"],
            "courseName": courseName.strip(),
            "learningDate": learningDate.strip()
        }
        
        app_logger.info(f"文件上传成功，数据已缓存 - 文件: {file.filename}, 课程: {courseName}, 日期: {learningDate}")
        
        return create_response(
            success=True,
            message="文件上传成功，可以开始同步",
            data={
                "filename": file.filename,
                "size": file_size,
                "headers": csv_validation["headers"],
                "encoding": csv_validation["encoding"],
                "preview_rows": csv_validation.get("preview_rows", 0),
                "courseName": courseName.strip(),
                "learningDate": learningDate.strip()
            }
        )
        
    except Exception as e:
        app_logger.error(f"文件上传失败: {e}", exc_info=True)
        return create_response(
            success=False,
            message=f"文件上传失败: {str(e)}"
        )

# 同步处理接口
@app.post("/api/sync")
async def sync_data():
    """执行数据同步"""
    global uploaded_file_data
    
    try:
        app_logger.info("开始同步数据处理...")
        
        # 检查是否有上传的文件
        if not uploaded_file_data:
            app_logger.error("同步失败: 没有上传的文件")
            return create_response(
                success=False,
                message="请先上传CSV文件"
            )
        
        # 检查配置
        if not config_manager.config:
            app_logger.error("同步失败: 配置未加载")
            return create_response(
                success=False,
                message="配置未加载，请检查配置文件"
            )
        
        # 验证配置
        validation_result = config_manager.validate_config(config_manager.config)
        if not validation_result["valid"]:
            app_logger.error(f"同步失败: 配置验证失败 - {validation_result.get('errors', [])}")
            return create_response(
                success=False,
                message="配置验证失败",
                data=validation_result
            )
        
        app_logger.info(f"开始同步数据: {uploaded_file_data['filename']}")
        app_logger.info(f"课程名称: {uploaded_file_data.get('courseName', 'N/A')}")
        app_logger.info(f"学习日期: {uploaded_file_data.get('learningDate', 'N/A')}")
        
        # 创建同步服务并执行同步
        sync_service = StudentSyncService(config_manager.config)
        
        app_logger.info("开始调用同步服务...")
        result = await sync_service.sync_csv_data(
            uploaded_file_data["content"],
            uploaded_file_data["filename"],
            course_name=uploaded_file_data.get("courseName"),
            learning_date=uploaded_file_data.get("learningDate")
        )
        
        app_logger.info(f"同步服务完成，结果: {result.get('success', False)}")
        
        if result.get("success"):
            app_logger.info("同步成功，清除上传文件数据")
            uploaded_file_data = None
        else:
            app_logger.error(f"同步失败: {result.get('message', '未知错误')}")
        
        return result
        
    except Exception as e:
        app_logger.error(f"同步过程发生异常: {str(e)}", exc_info=True)
        return create_response(
            success=False,
            message=f"同步过程发生异常: {str(e)}"
        )

# 同步状态查询接口
@app.get("/api/sync/status")
async def get_sync_status():
    """获取同步状态"""
    try:
        has_file = uploaded_file_data is not None
        has_config = config_manager.config is not None
        
        config_valid = False
        if has_config:
            validation_result = config_manager.validate_config(config_manager.config)
            config_valid = validation_result["valid"]
        
        return create_response(
            success=True,
            message="状态查询成功",
            data={
                "has_uploaded_file": has_file,
                "has_config": has_config,
                "config_valid": config_valid,
                "ready_to_sync": has_file and has_config and config_valid,
                "uploaded_file": {
                    "filename": uploaded_file_data["filename"] if has_file else None,
                    "size": uploaded_file_data["size"] if has_file else None
                } if has_file else None
            }
        )
        
    except Exception as e:
        app_logger.error(f"状态查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 清除上传文件接口
@app.delete("/api/upload/clear")
async def clear_uploaded_file():
    """清除已上传的文件"""
    global uploaded_file_data
    
    try:
        if uploaded_file_data:
            filename = uploaded_file_data["filename"]
            uploaded_file_data = None
            app_logger.info(f"已清除上传文件: {filename}")
            
            return create_response(
                success=True,
                message=f"已清除文件: {filename}"
            )
        else:
            return create_response(
                success=True,
                message="没有需要清除的文件"
            )
            
    except Exception as e:
        app_logger.error(f"清除文件失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 冲突更新接口
@app.post("/api/conflicts/update")
async def update_conflicts(request: Request):
    """更新选中的冲突字段"""
    try:
        # 获取请求数据
        data = await request.json()
        selected_conflicts = data.get("selected_conflicts", [])
        
        if not selected_conflicts:
            return create_response(
                success=False,
                message="没有选择要更新的冲突项"
            )
        
        # 检查配置
        if not config_manager.config:
            return create_response(
                success=False,
                message="配置未加载，请检查配置文件"
            )
        
        # 创建同步服务并执行冲突更新
        sync_service = StudentSyncService(config_manager.config)
        result = await sync_service.update_selected_conflicts(selected_conflicts)
        
        return create_response(
            success=result.get("success", False),
            message=result.get("message", "冲突更新完成"),
            data=result.get("data", {})
        )
        
    except Exception as e:
        app_logger.error(f"冲突更新失败: {e}", exc_info=True)
        return create_response(
            success=False,
            message=f"冲突更新失败: {str(e)}"
        )

# 示例CSV下载接口
@app.get("/api/sample-csv")
async def download_sample_csv():
    """下载示例CSV文件"""
    try:
        from backend.csv_processor import CSVProcessor
        
        processor = CSVProcessor()
        sample_content = processor.generate_sample_csv()
        
        from fastapi.responses import Response
        
        return Response(
            content=sample_content.encode('utf-8-sig'),  # 使用UTF-8 BOM以便Excel正确显示中文
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=sample_students.csv"
            }
        )
        
    except Exception as e:
        app_logger.error(f"生成示例CSV失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 关闭服务接口
@app.post("/api/shutdown")
async def shutdown_server():
    """优雅关闭服务器"""
    try:
        import asyncio
        import signal
        import os
        
        app_logger.info("收到关闭服务请求")
        
        # 立即返回响应
        response = create_response(
            success=True,
            message="服务器正在关闭，感谢使用！"
        )
        
        # 延迟1秒后关闭服务器，确保响应能够发送
        async def delayed_shutdown():
            await asyncio.sleep(1)
            app_logger.info("开始优雅关闭服务器...")
            
            # 清理资源
            global uploaded_file_data
            uploaded_file_data = None
            
            # 发送SIGTERM信号来优雅关闭
            os.kill(os.getpid(), signal.SIGTERM)
        
        # 在后台执行关闭任务
        asyncio.create_task(delayed_shutdown())
        
        return response
        
    except Exception as e:
        app_logger.error(f"关闭服务失败: {e}")
        return create_response(
            success=False,
            message=f"关闭服务失败: {str(e)}"
        )

# 错误处理中间件
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    app_logger.error(f"未处理的异常: {exc}")
    return create_response(
        success=False,
        message="服务器内部错误"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    ) 