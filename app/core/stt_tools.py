import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from ..utils.logger import logger


class STTTools:
    """STT工具类，封装stt-main的工具函数"""
    
    @staticmethod
    def setup_ffmpeg_path():
        """设置FFmpeg路径"""
        current_dir = Path(__file__).parent.parent.parent
        if sys.platform == 'win32':
            ffmpeg_path = current_dir / "stt-main"
            os.environ['PATH'] = f'{ffmpeg_path};{ffmpeg_path}/ffmpeg;' + os.environ['PATH']
        else:
            ffmpeg_path = current_dir / "stt-main"
            os.environ['PATH'] = f'{ffmpeg_path}:{ffmpeg_path}/ffmpeg:' + os.environ['PATH']
    
    @staticmethod
    def run_ffmpeg(args):
        """运行FFmpeg命令"""
        cmd = ["ffmpeg", "-hide_banner", "-y"] + args
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=0 if sys.platform != 'win32' else subprocess.CREATE_NO_WINDOW
            )
            
            while True:
                try:
                    outs, errs = process.communicate(timeout=0.5)
                    errs = str(errs)
                    if errs:
                        errs = errs.replace('\\\\', '\\').replace('\r', ' ').replace('\n', ' ')
                        errs = errs[errs.find("Error"):]
                    
                    if process.returncode == 0:
                        return "ok"
                    
                    return errs
                    
                except subprocess.TimeoutExpired:
                    pass
                except Exception as e:
                    errs = f"[error]ffmpeg:error {cmd=},\n{str(e)}"
                    return errs
                    
        except Exception as e:
            logger.error(f"FFmpeg execution failed: {e}")
            return str(e)
    
    @staticmethod
    def ms_to_time_string(ms=0, seconds=None):
        """将毫秒或秒转换为时间字符串格式"""
        if seconds is None:
            td = timedelta(milliseconds=ms)
        else:
            td = timedelta(seconds=seconds)
        
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = td.microseconds // 1000
        
        time_string = f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        return time_string
    
    @staticmethod
    def check_cuda_availability():
        """检查CUDA是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    @staticmethod
    def get_device_info():
        """获取设备信息"""
        device_info = {
            "cuda_available": False,
            "cuda_count": 0,
            "device_name": "CPU"
        }
        
        try:
            import torch
            device_info["cuda_available"] = torch.cuda.is_available()
            if device_info["cuda_available"]:
                device_info["cuda_count"] = torch.cuda.device_count()
                device_info["device_name"] = torch.cuda.get_device_name(0)
        except ImportError:
            pass
        
        return device_info
    
    @staticmethod
    def validate_audio_file(file_path: str) -> bool:
        """验证音频文件是否有效"""
        if not os.path.exists(file_path):
            return False
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False
        
        supported_extensions = ['.wav', '.mp3', '.mp4', '.m4a', '.flac', '.aac', '.mov', '.avi', '.mkv', '.mpeg']
        file_ext = Path(file_path).suffix.lower()
        
        return file_ext in supported_extensions
    
    @staticmethod
    def create_directories(base_path: str):
        """创建必要的目录"""
        paths = [
            Path(base_path) / "models",
            Path(base_path) / "temp",
            Path(base_path) / "output"
        ]
        
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)
        
        return paths
    
    @staticmethod
    def clean_filename(filename: str) -> str:
        """清理文件名，移除非法字符"""
        import re
        
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'_{2,}', '_', filename)
        filename = filename.strip('_')
        
        return filename if filename else "untitled"
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """格式化持续时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    @staticmethod
    def estimate_processing_time(file_size_mb: float, model_name: str, device: str) -> float:
        """估算处理时间（秒）"""
        base_time_per_mb = {
            "tiny": 0.5,
            "base": 1.0,
            "small": 2.0,
            "medium": 4.0,
            "large-v3": 8.0
        }
        
        multiplier = base_time_per_mb.get(model_name, 2.0)
        
        if device == "cuda":
            multiplier *= 0.3
        
        return file_size_mb * multiplier
    
    @staticmethod
    def get_file_info(file_path: str) -> dict:
        """获取文件信息"""
        if not os.path.exists(file_path):
            return None
        
        stat = os.stat(file_path)
        file_path_obj = Path(file_path)
        
        return {
            "name": file_path_obj.name,
            "size": stat.st_size,
            "size_mb": stat.st_size / (1024 * 1024),
            "extension": file_path_obj.suffix.lower(),
            "modified_time": stat.st_mtime
        }


class STTConfig:
    """STT配置管理类"""
    
    DEFAULT_SETTINGS = {
        "web_address": "127.0.0.1:9977",
        "lang": "zh",
        "devtype": "cpu",
        "cuda_com_type": "float32",
        "beam_size": 5,
        "best_of": 5,
        "vad": True,
        "temperature": 0,
        "condition_on_previous_text": False,
        "initial_prompt_zh": "转录为中文简体。"
    }
    
    @staticmethod
    def parse_stt_config(config_file: str = None) -> dict:
        """解析STT配置文件"""
        import re
        
        settings = STTConfig.DEFAULT_SETTINGS.copy()
        
        if not config_file or not os.path.exists(config_file):
            return settings
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f.readlines():
                    if not line.strip() or line.strip().startswith(";"):
                        continue
                    
                    line_parts = [x.strip() for x in line.strip().split('=', maxsplit=1)]
                    if len(line_parts) != 2:
                        continue
                    
                    key, value = line_parts
                    
                    if value == 'false':
                        settings[key] = False
                    elif value == 'true':
                        settings[key] = True
                    elif re.match(r'^\d+$', value):
                        settings[key] = int(value)
                    elif value.find(',') > 0:
                        settings[key] = value.split(',')
                    elif value:
                        settings[key] = str(value).lower()
        
        except Exception as e:
            logger.error(f"Failed to parse STT config: {e}")
        
        return settings
    
    @staticmethod
    def get_language_options():
        """获取语言选项"""
        return {
            "zh": {
                "中文": ['zh'],
                "英语": ['en'],
                "法语": ['fr'],
                "德语": ['de'],
                "日语": ['ja'],
                "韩语": ['ko'],
                "俄语": ['ru'],
                "西班牙语": ['es'],
                "泰国语": ['th'],
                "意大利语": ['it'],
                "葡萄牙语": ['pt'],
                "越南语": ['vi'],
                "阿拉伯语": ['ar'],
                "土耳其语": ['tr'],
                "匈牙利": ['hu'],
                "自动检测": ['auto']
            },
            "en": {
                "Chinese": ['zh'],
                "English": ['en'],
                "French": ['fr'],
                "German": ['de'],
                "Japanese": ['ja'],
                "Korean": ['ko'],
                "Russian": ['ru'],
                "Spanish": ['es'],
                "Thai": ['th'],
                "Italian": ['it'],
                "Portuguese": ['pt'],
                "Vietnamese": ['vi'],
                "Arabic": ['ar'],
                "Turkish": ['tr'],
                "Hungarian": ['hu'],
                "Automatic Detection": ['auto']
            }
        }
    
    @staticmethod
    def get_model_list():
        """获取可用模型列表"""
        return [
            "tiny",
            "base", 
            "small",
            "medium",
            "large-v3"
        ]