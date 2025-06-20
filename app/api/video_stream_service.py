import asyncio
import hashlib
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiofiles
from cachetools import TTLCache
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

dotenv_path = find_dotenv()
load_dotenv(dotenv_path)
CUSTOM_VIDEO_ROOT_DIR = os.getenv("CUSTOM_VIDEO_ROOT_DIR")
VIDEO_API_PORT = os.getenv("VIDEO_API_PORT") or 6007

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_VIDEO_ROOT_DIR = Path(os.path.split(os.path.realpath(sys.argv[0]))[0]).parent.parent / "downloads"
VIDEO_DIR = Path(CUSTOM_VIDEO_ROOT_DIR or DEFAULT_VIDEO_ROOT_DIR)
os.makedirs(VIDEO_DIR, exist_ok=True)

VIDEO_META_CACHE = TTLCache(maxsize=50, ttl=300)
CHUNK_CACHE = TTLCache(maxsize=25, ttl=60)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not VIDEO_DIR.exists():
        logger.error(f"Video directory does not exist: {VIDEO_DIR}")
        raise RuntimeError(f"Video directory does not exist: {VIDEO_DIR}")
    _app.mount("/api/videos", StaticFiles(directory=VIDEO_DIR), name="videos")
    yield

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    _app.mount("/api/videos", StaticFiles(directory=None))
    logger.info("Shutting down the application.")


app = FastAPI(lifespan=lifespan)


def validate_filename(filename: str):
    if re.search(r"[\\/]", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")


@app.get("/api/videos")
async def get_video(
        request: Request,
        filename: str = Query(...),
        subfolder: str | None = None
):

    cache_key = f"{filename}-{subfolder}"
    if meta := VIDEO_META_CACHE.get(cache_key):
        if_none_match = request.headers.get("If-None-Match")
        if_modified_since = request.headers.get("If-Modified-Since")

        if if_none_match and if_none_match == meta['etag']:
            return Response(status_code=304)

        if if_modified_since:
            last_modified = datetime.fromisoformat(meta['last_modified'])
            if datetime.strptime(if_modified_since, "%a, %d %b %Y %H:%M:%S GMT") >= last_modified:
                return Response(status_code=304)

    try:
        validate_filename(filename)
        if subfolder:
            video_path = VIDEO_DIR / subfolder / filename
        else:
            video_path = VIDEO_DIR / filename

    except Exception as e:
        logger.exception("Invalid filename or subfolder")
        raise e

    if not video_path.is_file():
        logger.error(f"File not found: {video_path}")
        raise HTTPException(status_code=404, detail="Video file not found")

    # Prevent path traversal attacks
    try:
        video_path.relative_to(VIDEO_DIR)
    except ValueError:
        logger.exception(f"Path traversal attempt: {video_path}")
        raise HTTPException(status_code=400, detail="Invalid file path")

    stat = video_path.stat()
    file_size = stat.st_size
    last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
    etag = hashlib.md5(f"{file_size}-{last_modified}".encode()).hexdigest()

    VIDEO_META_CACHE[cache_key] = {
        'etag': etag,
        'last_modified': last_modified,
        'file_size': file_size
    }

    # Parse Range header
    range_header = request.headers.get("Range")
    if range_header:
        start, end = range_header.replace("bytes=", "").split("-")
        start = int(start)
        end = int(end) if end else file_size - 1

        if start >= file_size or end >= file_size:
            logger.error(f"Invalid range request: {range_header}, file size: {file_size}")
            raise HTTPException(status_code=416, detail="Requested range not satisfiable")

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(
            file_sender_range(video_path, start, end),
            status_code=206,
            headers=headers,
        )

    # If no Range header, return the whole file
    headers = {
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
        "Cache-Control": "public, max-age=300",
        "ETag": etag,
        "Last-Modified": datetime.fromisoformat(last_modified).strftime("%a, %d %b %Y %H:%M:%S GMT")
    }
    try:
        return StreamingResponse(file_sender(video_path), headers=headers)
    except Exception:
        logger.exception("Streaming error")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# Async file sender (full content)
async def file_sender(video_path: Path):
    async with aiofiles.open(video_path, "rb") as file:
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            yield chunk


# Async file sender (range content)
async def file_sender_range(video_path: Path, start: int, end: int):
    cache_key = f"{video_path.name}-{start}-{end}"

    if cached := CHUNK_CACHE.get(cache_key):
        yield cached
        return

    async with aiofiles.open(video_path, "rb") as file:
        await file.seek(start)
        chunks = []
        while start <= end:
            chunk_size = min(65536, end - start + 1)
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
            start += len(chunk)

        full_chunk = b"".join(chunks)
        if len(full_chunk) < 1024 * 1024:
            CHUNK_CACHE[cache_key] = full_chunk
        yield full_chunk


if __name__ == "__main__":
    import uvicorn
    import json
    import tempfile
    import uuid
    from pathlib import Path

    # STT相关端点
    STT_TASKS = {}  # 存储STT任务状态

    @app.post("/api/stt/upload")
    async def upload_audio_for_stt(
        file: UploadFile = File(...),
        language: str = Form("auto"),
        model: str = Form("base"),
        response_format: str = Form("srt")
    ):
        """上传音频文件进行语音转文字处理"""
        try:
            # 验证文件类型
            if not file.filename:
                raise HTTPException(status_code=400, detail="No file provided")
            
            file_extension = Path(file.filename).suffix.lower()
            supported_extensions = ['.wav', '.mp3', '.mp4', '.m4a', '.flac', '.aac', '.mov', '.avi', '.mkv', '.mpeg']
            
            if file_extension not in supported_extensions:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file format: {file_extension}"
                )
            
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 保存上传的文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                content = await file.read()
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            # 初始化任务状态
            STT_TASKS[task_id] = {
                "status": "uploaded",
                "progress": 0,
                "message": "文件上传成功",
                "file_path": temp_file_path,
                "filename": file.filename,
                "config": {
                    "language": language,
                    "model": model,
                    "response_format": response_format
                },
                "result": None,
                "error": None
            }
            
            return JSONResponse({
                "code": 0,
                "message": "文件上传成功",
                "data": {
                    "task_id": task_id,
                    "filename": file.filename,
                    "file_size": len(content)
                }
            })
            
        except Exception as e:
            logger.exception("Failed to upload audio file for STT")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/stt/process/{task_id}")
    async def process_stt_task(task_id: str):
        """开始处理STT任务"""
        try:
            if task_id not in STT_TASKS:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = STT_TASKS[task_id]
            if task["status"] == "processing":
                return JSONResponse({
                    "code": 1,
                    "message": "任务正在处理中",
                    "data": {"task_id": task_id}
                })
            
            # 导入STT管理器
            try:
                from ..core.stt_manager import STTManager
                from ..models.stt_model import STTConfig
                
                # 创建临时应用对象
                class TempApp:
                    def __init__(self):
                        self.settings = self
                        self.user_config = STTConfig.get_default_config()
                        self.user_config.update({
                            "stt_model": task["config"]["model"],
                            "stt_language": task["config"]["language"],
                            "stt_output_format": task["config"]["response_format"]
                        })
                        self.language_manager = self
                        self.language = {"stt_manager": {}}
                    
                    def add_observer(self, observer):
                        pass
                
                temp_app = TempApp()
                stt_manager = STTManager(temp_app)
                
                if not stt_manager.is_available:
                    task["status"] = "error"
                    task["error"] = "STT功能不可用"
                    return JSONResponse({
                        "code": 1,
                        "message": "STT功能不可用",
                        "data": {"task_id": task_id}
                    })
                
                # 更新任务状态
                task["status"] = "processing"
                task["progress"] = 0.1
                task["message"] = "开始处理..."
                
                # 处理音频文件
                def progress_callback(progress, message):
                    task["progress"] = progress
                    task["message"] = message
                
                result = await stt_manager.transcribe_audio(
                    task["file_path"],
                    task_id,
                    temp_app.user_config,
                    progress_callback
                )
                
                if result["success"]:
                    task["status"] = "completed"
                    task["result"] = result["data"]
                    task["progress"] = 1.0
                    task["message"] = "处理完成"
                else:
                    task["status"] = "error"
                    task["error"] = result["error"]
                    task["message"] = f"处理失败: {result['error']}"
                
                return JSONResponse({
                    "code": 0,
                    "message": "处理已开始",
                    "data": {"task_id": task_id}
                })
                
            except ImportError:
                task["status"] = "error"
                task["error"] = "STT依赖未安装"
                return JSONResponse({
                    "code": 1,
                    "message": "STT依赖未安装",
                    "data": {"task_id": task_id}
                })
                
        except Exception as e:
            logger.exception("Failed to process STT task")
            if task_id in STT_TASKS:
                STT_TASKS[task_id]["status"] = "error"
                STT_TASKS[task_id]["error"] = str(e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/stt/status/{task_id}")
    async def get_stt_task_status(task_id: str):
        """获取STT任务状态"""
        try:
            if task_id not in STT_TASKS:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = STT_TASKS[task_id]
            
            return JSONResponse({
                "code": 0,
                "message": "获取状态成功",
                "data": {
                    "task_id": task_id,
                    "status": task["status"],
                    "progress": task["progress"],
                    "message": task["message"],
                    "filename": task["filename"],
                    "result": task["result"] if task["status"] == "completed" else None,
                    "error": task["error"] if task["status"] == "error" else None
                }
            })
            
        except Exception as e:
            logger.exception("Failed to get STT task status")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/stt/download/{task_id}")
    async def download_stt_result(task_id: str):
        """下载STT处理结果"""
        try:
            if task_id not in STT_TASKS:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = STT_TASKS[task_id]
            
            if task["status"] != "completed":
                raise HTTPException(status_code=400, detail="Task not completed")
            
            if not task["result"]:
                raise HTTPException(status_code=404, detail="No result available")
            
            response_format = task["config"]["response_format"]
            filename = f"{Path(task['filename']).stem}.{response_format}"
            
            if response_format == "json":
                content = json.dumps(task["result"], ensure_ascii=False, indent=2)
                media_type = "application/json"
            else:
                content = task["result"]
                media_type = "text/plain"
            
            return Response(
                content=content.encode('utf-8'),
                media_type=media_type,
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
            
        except Exception as e:
            logger.exception("Failed to download STT result")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/stt/task/{task_id}")
    async def delete_stt_task(task_id: str):
        """删除STT任务"""
        try:
            if task_id not in STT_TASKS:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = STT_TASKS[task_id]
            
            # 删除临时文件
            try:
                if os.path.exists(task["file_path"]):
                    os.unlink(task["file_path"])
            except Exception:
                pass
            
            # 删除任务记录
            del STT_TASKS[task_id]
            
            return JSONResponse({
                "code": 0,
                "message": "任务删除成功",
                "data": {"task_id": task_id}
            })
            
        except Exception as e:
            logger.exception("Failed to delete STT task")
            raise HTTPException(status_code=500, detail=str(e))

    uvicorn.run(app, host="0.0.0.0", port=int(VIDEO_API_PORT), log_level="debug")
