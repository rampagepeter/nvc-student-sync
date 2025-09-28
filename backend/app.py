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
from backend.cache_manager import StudentCacheManager
from backend.mapping_memory import MappingMemory

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

# 全局变量存储上传的文件数据和字段映射
uploaded_file_data = None
current_field_mapping = None

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
        
        # 检查是否需要字段映射
        # 如果所有CSV字段都能在默认映射中找到，则不需要互动配置
        from .sync_service import FieldMappingService
        default_mapping = FieldMappingService.DEFAULT_FIELD_MAPPING
        csv_headers = csv_validation["headers"]

        # 检查是否有未映射的字段（排除核心字段和已知字段）
        # 核心字段：这些字段会被CSV处理器自动处理
        core_fields = {"user_id", "nickname", "phone", "course", "learning_date"}
        # 已知字段的所有可能变体
        known_field_variants = set()
        for field in default_mapping.keys():
            known_field_variants.add(field)
            # 添加常见的变体
            known_field_variants.add(field.replace(" ", ""))  # 去除空格
            known_field_variants.add(field.replace("　", ""))  # 去除全角空格

        unmapped_fields = []
        mapped_fields = []

        for header in csv_headers:
            # 标准化字段名（去除空格等）
            normalized_header = header.strip().replace(" ", "").replace("　", "")

            # 检查是否是核心字段
            if any(core in normalized_header.lower() for core in ["userid", "用户id", "昵称", "nickname", "手机", "phone"]):
                mapped_fields.append(header)
                continue

            # 检查是否在默认映射中
            if header in default_mapping or normalized_header in known_field_variants:
                mapped_fields.append(header)
            else:
                unmapped_fields.append(header)

        # 只有当有未映射字段时才需要显示映射界面
        need_mapping = len(unmapped_fields) > 0

        if need_mapping:
            app_logger.info(f"检测到 {len(unmapped_fields)} 个未映射的字段: {unmapped_fields}")
            app_logger.info(f"已知映射的字段: {mapped_fields}")
        else:
            app_logger.info(f"所有字段都可以使用默认映射，无需互动配置。已映射字段: {mapped_fields}")

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
                "learningDate": learningDate.strip(),
                "need_mapping": need_mapping,
                "csv_headers": csv_validation["headers"],
                "unmapped_fields": unmapped_fields if need_mapping else []
            }
        )
        
    except Exception as e:
        app_logger.error(f"文件上传失败: {e}", exc_info=True)
        return create_response(
            success=False,
            message=f"文件上传失败: {str(e)}"
        )

# 获取表格字段信息接口
@app.get("/api/table/fields")
async def get_table_fields():
    """获取飞书表格字段信息"""
    try:
        app_logger.info("获取飞书表格字段信息")

        # 检查配置
        if not config_manager.config:
            app_logger.error("配置未加载")
            return create_response(
                success=False,
                message="配置未加载，请检查配置文件"
            )

        # 验证配置
        validation_result = config_manager.validate_config(config_manager.config)
        if not validation_result["valid"]:
            app_logger.error(f"配置验证失败: {validation_result.get('errors', [])}")
            return create_response(
                success=False,
                message="配置验证失败",
                data=validation_result
            )

        # 创建同步服务并获取字段信息
        sync_service = StudentSyncService(config_manager.config)
        fields_info = await sync_service.get_table_fields_info()

        app_logger.info("飞书表格字段信息获取成功")
        return create_response(
            success=True,
            message="字段信息获取成功",
            data=fields_info
        )

    except Exception as e:
        app_logger.error(f"获取表格字段信息失败: {e}", exc_info=True)
        return create_response(
            success=False,
            message=f"获取表格字段信息失败: {str(e)}"
        )

# 设置字段映射接口
@app.post("/api/mapping/set")
async def set_field_mapping(request: dict):
    """设置字段映射配置"""
    global current_field_mapping

    try:
        mapping = request.get('mapping', {})

        if not isinstance(mapping, dict):
            return create_response(
                success=False,
                message="映射配置格式错误"
            )

        current_field_mapping = mapping
        app_logger.info(f"字段映射配置已保存: {len(mapping)} 个映射")

        return create_response(
            success=True,
            message="字段映射配置成功",
            data={
                "mapping_count": len(mapping)
            }
        )

    except Exception as e:
        app_logger.error(f"设置字段映射失败: {e}", exc_info=True)
        return create_response(
            success=False,
            message=f"设置字段映射失败: {str(e)}"
        )

# 同步处理接口
@app.post("/api/sync")
async def sync_data():
    """执行数据同步"""
    global uploaded_file_data, current_field_mapping
    
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
        # 添加字段映射信息到日志
        if current_field_mapping:
            app_logger.info(f"使用自定义字段映射: {len(current_field_mapping)} 个映射")
            for csv_field, feishu_field in current_field_mapping.items():
                app_logger.info(f"  {csv_field} → {feishu_field}")
        else:
            app_logger.info("使用默认字段映射")

        result = await sync_service.sync_csv_data(
            uploaded_file_data["content"],
            uploaded_file_data["filename"],
            course_name=uploaded_file_data.get("courseName"),
            learning_date=uploaded_file_data.get("learningDate"),
            field_mapping=current_field_mapping
        )
        
        app_logger.info(f"同步服务完成，结果: {result.get('success', False)}")
        
        if result.get("success"):
            app_logger.info("同步成功，清除上传文件数据和映射配置")
            uploaded_file_data = None
            current_field_mapping = None
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

# 缓存管理接口
@app.get("/api/cache/status")
async def get_cache_status():
    """获取缓存状态"""
    try:
        import json
        from datetime import datetime
        from pathlib import Path

        cache_dir = Path("cache")
        cache_file = cache_dir / "students_cache.pkl"
        meta_file = cache_dir / "cache_meta.json"

        # 检查缓存文件是否存在
        if not cache_file.exists() or not meta_file.exists():
            return create_response(
                success=True,
                message="缓存状态获取成功",
                data={
                    "cache_exists": False,
                    "total_records": 0,
                    "last_update": None,
                    "age_hours": None,
                    "message": "缓存文件不存在，建议刷新缓存"
                }
            )

        # 读取缓存元信息
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)

            last_update = datetime.fromisoformat(meta['last_update'])
            age_hours = (datetime.now() - last_update).total_seconds() / 3600

            # 根据缓存年龄给出建议
            if age_hours > 168:  # 超过7天
                message = f"缓存较旧（{age_hours:.0f}小时前），建议刷新"
            else:
                message = f"缓存就绪（{meta['total_records']}条记录）"

            return create_response(
                success=True,
                message="缓存状态获取成功",
                data={
                    "cache_exists": True,
                    "total_records": meta.get('total_records', 0),
                    "unique_users": meta.get('unique_users', 0),
                    "last_update": meta.get('last_update'),
                    "age_hours": round(age_hours, 1),
                    "message": message
                }
            )
        except Exception as e:
            app_logger.error(f"读取缓存元信息失败: {e}")
            return create_response(
                success=True,
                message="缓存状态获取成功",
                data={
                    "cache_exists": True,
                    "error": "无法读取缓存信息",
                    "message": "缓存文件可能损坏，建议刷新缓存"
                }
            )

    except Exception as e:
        app_logger.error(f"获取缓存状态失败: {e}")
        return create_response(
            success=False,
            message=f"获取缓存状态失败: {str(e)}"
        )

@app.post("/api/cache/refresh")
async def refresh_cache():
    """刷新缓存"""
    try:
        # 检查配置
        if not config_manager.config:
            return create_response(
                success=False,
                message="配置未加载，请检查配置文件"
            )

        # 创建缓存管理器和飞书客户端
        cache_manager = StudentCacheManager()
        from backend.feishu_client import FeishuClient

        async with FeishuClient(config_manager.config) as feishu_client:
            # 获取学员表配置
            student_table = config_manager.config.student_table

            # 加载所有学员到缓存
            success = await cache_manager.load_all_students(
                feishu_client, student_table
            )

            if success:
                stats = cache_manager.get_cache_stats()
                return create_response(
                    success=True,
                    message=f"缓存刷新成功，共加载 {stats['total_records']} 条记录",
                    data=stats
                )
            else:
                return create_response(
                    success=False,
                    message="缓存刷新失败"
                )

    except Exception as e:
        app_logger.error(f"刷新缓存失败: {e}")
        return create_response(
            success=False,
            message=f"刷新缓存失败: {str(e)}"
        )

@app.post("/api/cache/clear")
async def clear_cache():
    """清空缓存"""
    try:
        cache_manager = StudentCacheManager()
        cache_manager.clear_cache()

        return create_response(
            success=True,
            message="缓存已清空"
        )
    except Exception as e:
        app_logger.error(f"清空缓存失败: {e}")
        return create_response(
            success=False,
            message=f"清空缓存失败: {str(e)}"
        )


# 字段映射配置接口
@app.post("/api/mapping/get-suggestion")
async def get_mapping_suggestion(request_data: dict):
    """获取字段映射建议（基于历史记录）"""
    try:
        csv_headers = request_data.get("csv_headers", [])

        if not csv_headers:
            return create_response(
                success=False,
                message="CSV字段列表不能为空"
            )

        # 检查配置
        if not config_manager.config:
            return create_response(
                success=False,
                message="配置未加载，请检查配置文件"
            )

        # 获取飞书表格字段
        sync_service = StudentSyncService(config_manager.config)
        feishu_fields_info = await sync_service.get_table_fields_info()

        if not feishu_fields_info["success"]:
            return create_response(
                success=False,
                message=f"获取飞书表格字段失败: {feishu_fields_info['message']}"
            )

        feishu_fields = feishu_fields_info["data"]["student_table"]["fields"]

        # 获取历史映射建议
        mapping_memory = MappingMemory()
        suggested_mapping = mapping_memory.get_last_mapping_for_csv(csv_headers)

        return create_response(
            success=True,
            message="映射建议获取成功",
            data={
                "csv_headers": csv_headers,
                "feishu_fields": feishu_fields,
                "suggestion": suggested_mapping,
                "has_history": suggested_mapping is not None
            }
        )

    except Exception as e:
        app_logger.error(f"获取映射建议失败: {e}")
        return create_response(
            success=False,
            message=f"获取映射建议失败: {str(e)}"
        )

@app.post("/api/mapping/save")
async def save_mapping(request_data: dict):
    """保存字段映射配置"""
    try:
        csv_headers = request_data.get("csv_headers", [])
        mapping = request_data.get("mapping", {})

        if not csv_headers or not mapping:
            return create_response(
                success=False,
                message="CSV字段列表和映射配置不能为空"
            )

        # 保存映射配置
        mapping_memory = MappingMemory()
        success = mapping_memory.save_mapping(csv_headers, mapping)

        if success:
            app_logger.info(f"保存字段映射成功: {len(mapping)}个字段")
            return create_response(
                success=True,
                message="映射配置保存成功"
            )
        else:
            return create_response(
                success=False,
                message="映射配置保存失败"
            )

    except Exception as e:
        app_logger.error(f"保存映射配置失败: {e}")
        return create_response(
            success=False,
            message=f"保存映射配置失败: {str(e)}"
        )

@app.get("/api/mapping/history")
async def get_mapping_history():
    """获取映射历史记录"""
    try:
        mapping_memory = MappingMemory()
        history = mapping_memory.get_mapping_history()
        statistics = mapping_memory.get_mapping_statistics()

        return create_response(
            success=True,
            data={
                "history": history,
                "statistics": statistics
            }
        )

    except Exception as e:
        app_logger.error(f"获取映射历史失败: {e}")
        return create_response(
            success=False,
            message=f"获取映射历史失败: {str(e)}"
        )

@app.delete("/api/mapping/clear")
async def clear_mapping_history():
    """清除映射历史记录"""
    try:
        mapping_memory = MappingMemory()
        success = mapping_memory.clear_history()

        if success:
            app_logger.info("清除映射历史成功")
            return create_response(
                success=True,
                message="映射历史已清除"
            )
        else:
            return create_response(
                success=False,
                message="清除映射历史失败"
            )

    except Exception as e:
        app_logger.error(f"清除映射历史失败: {e}")
        return create_response(
            success=False,
            message=f"清除映射历史失败: {str(e)}"
        )

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