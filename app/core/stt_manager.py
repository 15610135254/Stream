import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from ..process_manager import BackgroundService
from ..utils.logger import logger


class STTProgress:
    """STT处理进度管理"""
    
    def __init__(self):
        self.progress_data = {}
        self.lock = threading.Lock()
    
    def set_progress(self, task_id: str, progress: float, message: str = ""):
        with self.lock:
            self.progress_data[task_id] = {
                "progress": progress,
                "message": message,
                "timestamp": time.time()
            }
    
    def get_progress(self, task_id: str) -> dict:
        with self.lock:
            return self.progress_data.get(task_id, {"progress": 0, "message": "", "timestamp": 0})
    
    def clear_progress(self, task_id: str):
        with self.lock:
            self.progress_data.pop(task_id, None)


class STTManager:
    """音频转文字管理器"""
    
    def __init__(self, app):
        self.app = app
        self.settings = app.settings
        self.progress_manager = STTProgress()
        self.is_available = False
        self.model_cache = {}
        self.app.language_manager.add_observer(self)
        self._ = {}
        self.load()
        self.initialize()
    
    def load(self):
        """加载语言配置"""
        language = self.app.language_manager.language
        self._.update(language.get("stt_manager", {}))
    
    def initialize(self):
        """初始化STT管理器"""
        try:
            from faster_whisper import WhisperModel
            self.WhisperModel = WhisperModel
            self.is_available = True
            logger.info("STT Manager initialized successfully")
        except ImportError as e:
            logger.warning(f"STT dependencies not available: {e}")
            self.is_available = False
    
    def get_stt_config(self) -> dict:
        """获取STT配置"""
        user_config = self.settings.user_config
        
        # 自动检测设备，如果用户没有明确设置设备类型
        default_device = self.get_recommended_device()
        
        return {
            "enabled": user_config.get("stt_enabled", False),
            "auto_process": user_config.get("stt_auto_process", False),
            "model": user_config.get("stt_model", "base"),
            "language": user_config.get("stt_language", "auto"),
            "output_format": user_config.get("stt_output_format", "srt"),
            "device": user_config.get("stt_device", default_device),
            "model_path": user_config.get("stt_model_path", "./models"),
            "beam_size": user_config.get("stt_beam_size", 5),
            "best_of": user_config.get("stt_best_of", 5),
            "temperature": user_config.get("stt_temperature", 0),
            "vad_filter": user_config.get("stt_vad_filter", True),
            "condition_on_previous_text": user_config.get("stt_condition_on_previous_text", False),
            "initial_prompt_zh": user_config.get("stt_initial_prompt_zh", "以下是普通话内容，请转录为中文简体。")
        }
    
    def get_model_path(self, model_name: str) -> str:
        """获取模型路径"""
        config = self.get_stt_config()
        model_dir = Path(config["model_path"])
        
        if model_name.find('/') > 0:
            return model_name
        
        if model_name.startswith('distil'):
            model_path = model_dir / f"models--Systran--faster-{model_name}" / "snapshots"
        else:
            model_path = model_dir / f"models--Systran--faster-whisper-{model_name}" / "snapshots"
        
        return str(model_path.parent) if model_path.exists() else model_name
    
    def get_recommended_device(self) -> str:
        """获取推荐的设备类型（GPU优先，无GPU则CPU）"""
        if not self.is_available:
            return "cpu"
        
        try:
            import torch
            if torch.cuda.is_available():
                device_count = torch.cuda.device_count()
                if device_count > 0:
                    logger.info(f"检测到 {device_count} 个CUDA设备，推荐使用GPU")
                    return "cuda"
            logger.info("未检测到可用的CUDA设备，推荐使用CPU")
            return "cpu"
        except Exception as e:
            logger.warning(f"设备检测失败: {e}，默认使用CPU")
            return "cpu"
    
    def get_device_info(self) -> dict:
        """获取详细的设备信息"""
        info = {
            "cuda_available": False,
            "cuda_count": 0,
            "cuda_devices": [],
            "recommended_device": "cpu"
        }
        
        if not self.is_available:
            return info
        
        try:
            import torch
            info["cuda_available"] = torch.cuda.is_available()
            
            if info["cuda_available"]:
                info["cuda_count"] = torch.cuda.device_count()
                info["recommended_device"] = "cuda"
                
                for i in range(info["cuda_count"]):
                    device_name = torch.cuda.get_device_name(i)
                    device_memory = torch.cuda.get_device_properties(i).total_memory / (1024**3)  # GB
                    info["cuda_devices"].append({
                        "id": i,
                        "name": device_name,
                        "memory_gb": round(device_memory, 1)
                    })
            else:
                info["recommended_device"] = "cpu"
                
        except Exception as e:
            logger.warning(f"获取设备信息失败: {e}")
        
        return info
    
    def is_model_available(self, model_name: str) -> bool:
        """检查模型是否可用（本地存在或可下载）"""
        if not self.is_available:
            return False
        
        # 远程模型始终可用（需要网络）
        if model_name.find('/') > 0:
            return True
        
        # 检查本地是否已下载
        model_path = self.get_model_path(model_name)
        if Path(model_path).exists():
            return True
        
        # 基础模型可以从HuggingFace自动下载
        return True
    
    def get_model(self, model_name: str, device: str = "cpu", compute_type: str = "float32"):
        """获取或创建Whisper模型实例"""
        if not self.is_available:
            raise RuntimeError("STT dependencies not available")
        
        cache_key = f"{model_name}_{device}_{compute_type}"
        
        if cache_key in self.model_cache:
            return self.model_cache[cache_key]
        
        try:
            # 检查模型是否本地存在
            config = self.get_stt_config()
            model_dir = Path(config["model_path"])
            
            # 确定实际的模型名称和路径
            actual_model_name = model_name
            if model_name.startswith('distil'):
                actual_model_name = model_name.replace('-whisper', '')
            
            # 检查本地模型路径
            if model_name.find('/') > 0:
                # 远程模型，直接使用模型名
                model_path = model_name
                local_files_only = False
            else:
                # 本地模型，先检查是否存在
                if model_name.startswith('distil'):
                    local_model_path = model_dir / f"models--Systran--faster-{model_name}" / "snapshots"
                else:
                    local_model_path = model_dir / f"models--Systran--faster-whisper-{model_name}" / "snapshots"
                
                if local_model_path.exists():
                    # 本地已存在，使用本地路径
                    model_path = str(local_model_path.parent)
                    local_files_only = True
                else:
                    # 本地不存在，使用模型名让faster-whisper自动下载
                    model_path = actual_model_name
                    local_files_only = False
            
            model = self.WhisperModel(
                model_path,
                device=device,
                compute_type=compute_type,
                download_root=config["model_path"],
                local_files_only=local_files_only
            )
            
            self.model_cache[cache_key] = model
            return model
            
        except Exception as e:
            if model_name.find('/') > 0:
                error_msg = f'从huggingface.co下载远程模型 {model_name} 失败，请检查网络连接'
            else:
                error_msg = f'加载或下载模型 {model_name} 失败，请检查网络连接'
            raise RuntimeError(f"{error_msg}: {str(e)}")
    
    def extract_audio_from_video(self, video_path: str, output_path: str) -> bool:
        """从视频文件提取音频"""
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-y",
                "-i", video_path,
                "-ar", "16000",
                "-ac", "1",
                "-vn",
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                return True
            else:
                logger.error(f"Extract audio failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Extract audio error: {e}")
            return False
    
    def clean_text(self, text: str) -> str:
        """清理转录文本"""
        if not text:
            return ""
        
        text = text.strip().replace('&#39;', "'")
        text = re.sub(r'&#\d+;', '', text)
        
        if re.match(r'^[，。、？''""；：（｛｝【】）:;"\'\\s \\d`!@#$%^&*()_+=.,?/\\-]*$', text) or len(text) <= 1:
            return ""
        
        return text
    
    def format_time_string(self, milliseconds: int) -> str:
        """格式化时间字符串"""
        hours = milliseconds // 3600000
        minutes = (milliseconds % 3600000) // 60000
        seconds = (milliseconds % 60000) // 1000
        ms = milliseconds % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"
    
    async def transcribe_audio(
        self,
        audio_path: str,
        task_id: str,
        config: Optional[dict] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> dict:
        """转录音频文件"""
        if not self.is_available:
            raise RuntimeError("STT functionality not available")
        
        if config is None:
            config = self.get_stt_config()
        
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        try:
            self.progress_manager.set_progress(task_id, 0.1, "正在加载模型...")
            if progress_callback:
                progress_callback(0.1, "正在加载模型...")
            
            model = self.get_model(
                config["model"],
                config["device"],
                "float32" if config["device"] == "cpu" else "float16"
            )
            
            self.progress_manager.set_progress(task_id, 0.2, "开始转录...")
            if progress_callback:
                progress_callback(0.2, "开始转录...")
            
            segments, info = model.transcribe(
                audio_path,
                beam_size=config["beam_size"],
                best_of=config["best_of"],
                temperature=config["temperature"] if config["temperature"] > 0 else 0,
                condition_on_previous_text=config["condition_on_previous_text"],
                vad_filter=config["vad_filter"],
                language=config["language"] if config["language"] != 'auto' else None,
                initial_prompt=config["initial_prompt_zh"] if config["language"] == 'zh' else None
            )
            
            total_duration = round(info.duration, 2)
            result_data = []
            
            for segment in segments:
                progress = 0.2 + (segment.end / total_duration) * 0.7
                self.progress_manager.set_progress(task_id, progress, f"处理中: {segment.end:.1f}s/{total_duration:.1f}s")
                if progress_callback:
                    progress_callback(progress, f"处理中: {segment.end:.1f}s/{total_duration:.1f}s")
                
                text = self.clean_text(segment.text)
                if not text:
                    continue
                
                start_ms = int(segment.start * 1000)
                end_ms = int(segment.end * 1000)
                start_time = self.format_time_string(start_ms)
                end_time = self.format_time_string(end_ms)
                
                if config["output_format"] == 'json':
                    result_data.append({
                        "line": len(result_data) + 1,
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": text
                    })
                elif config["output_format"] == 'text':
                    result_data.append(text)
                else:  # srt format
                    result_data.append(f'{len(result_data) + 1}\n{start_time} --> {end_time}\n{text}\n')
            
            self.progress_manager.set_progress(task_id, 1.0, "转录完成")
            if progress_callback:
                progress_callback(1.0, "转录完成")
            
            if config["output_format"] == 'json':
                final_result = result_data
            else:
                final_result = "\n".join(result_data)
            
            return {
                "success": True,
                "data": final_result,
                "duration": total_duration,
                "language": info.language,
                "language_probability": info.language_probability
            }
            
        except Exception as e:
            error_msg = f"转录失败: {str(e)}"
            self.progress_manager.set_progress(task_id, 0, error_msg)
            if progress_callback:
                progress_callback(0, error_msg)
            logger.error(error_msg)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def process_recording_file(
        self,
        recording_path: str,
        task_id: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> dict:
        """处理录制文件，生成字幕"""
        if task_id is None:
            task_id = f"stt_{int(time.time())}"
        
        config = self.get_stt_config()
        if not config["enabled"]:
            return {"success": False, "error": "STT功能未启用"}
        
        recording_path = Path(recording_path)
        if not recording_path.exists():
            return {"success": False, "error": f"文件不存在: {recording_path}"}
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_path = Path(temp_dir) / "audio.wav"
                
                if recording_path.suffix.lower() in ['.wav']:
                    shutil.copy2(recording_path, audio_path)
                else:
                    self.progress_manager.set_progress(task_id, 0.05, "提取音频...")
                    if progress_callback:
                        progress_callback(0.05, "提取音频...")
                    
                    if not self.extract_audio_from_video(str(recording_path), str(audio_path)):
                        return {"success": False, "error": "音频提取失败"}
                
                result = await self.transcribe_audio(audio_path, task_id, config, progress_callback)
                
                if result["success"]:
                    output_path = recording_path.with_suffix(f'.{config["output_format"]}')
                    
                    if config["output_format"] == 'json':
                        import json
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(result["data"], f, ensure_ascii=False, indent=2)
                    else:
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(result["data"])
                    
                    result["output_path"] = str(output_path)
                    logger.success(f"STT处理完成: {output_path}")
                
                return result
                
        except Exception as e:
            error_msg = f"处理录制文件失败: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        finally:
            self.progress_manager.clear_progress(task_id)
    
    async def process_recording_async(
        self,
        recording_path: str,
        task_id: Optional[str] = None
    ):
        """异步处理录制文件（用于后台服务）"""
        if not self.app.recording_enabled:
            logger.info(f"应用正在关闭，将STT任务添加到后台服务: {recording_path}")
            BackgroundService.get_instance().add_task(
                self.process_recording_sync, recording_path, task_id
            )
            return
        
        await self.process_recording_file(recording_path, task_id)
    
    def process_recording_sync(self, recording_path: str, task_id: Optional[str] = None):
        """同步版本的录制文件处理（用于后台服务）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.process_recording_file(recording_path, task_id))
        finally:
            loop.close()
    
    def get_progress(self, task_id: str) -> dict:
        """获取处理进度"""
        return self.progress_manager.get_progress(task_id)
    
    def get_available_models(self) -> list:
        """获取可用的模型列表"""
        from ..core.stt_tools import STTConfig
        models = STTConfig.get_model_list()
        available_models = []
        
        for model in models:
            if self.is_model_available(model):
                available_models.append(model)
        
        return available_models if available_models else models
    
    def get_supported_languages(self) -> dict:
        """获取支持的语言列表"""
        return {
            "auto": "自动检测",
            "zh": "中文",
            "en": "英语",
            "fr": "法语",
            "de": "德语",
            "ja": "日语",
            "ko": "韩语",
            "ru": "俄语",
            "es": "西班牙语",
            "th": "泰语",
            "it": "意大利语",
            "pt": "葡萄牙语",
            "vi": "越南语",
            "ar": "阿拉伯语",
            "tr": "土耳其语",
            "hu": "匈牙利语"
        }
    
    def get_output_formats(self) -> list:
        """获取支持的输出格式"""
        return ["srt", "json", "text"]