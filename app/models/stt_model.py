from enum import Enum


class STTModel(Enum):
    """STT模型选项"""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V3 = "large-v3"
    DISTIL_TINY = "distil-tiny-whisper"
    DISTIL_SMALL = "distil-small-whisper"
    DISTIL_MEDIUM = "distil-medium-whisper"
    DISTIL_LARGE_V3 = "distil-large-v3-whisper"

    @classmethod
    def get_models(cls):
        """获取所有模型选项"""
        return [model.value for model in cls]

    @classmethod
    def get_local_models(cls):
        """获取本地模型选项（不需要网络下载）"""
        return [cls.TINY.value, cls.BASE.value, cls.SMALL.value, cls.MEDIUM.value, cls.LARGE_V3.value]

    @classmethod
    def get_distil_models(cls):
        """获取distil模型选项"""
        return [cls.DISTIL_TINY.value, cls.DISTIL_SMALL.value, cls.DISTIL_MEDIUM.value, cls.DISTIL_LARGE_V3.value]


class STTLanguage(Enum):
    """STT语言选项"""
    AUTO = "auto"
    CHINESE = "zh"
    ENGLISH = "en"
    FRENCH = "fr"
    GERMAN = "de"
    JAPANESE = "ja"
    KOREAN = "ko"
    RUSSIAN = "ru"
    SPANISH = "es"
    THAI = "th"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    VIETNAMESE = "vi"
    ARABIC = "ar"
    TURKISH = "tr"
    HUNGARIAN = "hu"

    @classmethod
    def get_languages(cls):
        """获取所有语言选项"""
        return [lang.value for lang in cls]

    @classmethod
    def get_language_names(cls):
        """获取语言名称映射"""
        return {
            cls.AUTO.value: "自动检测",
            cls.CHINESE.value: "中文",
            cls.ENGLISH.value: "英语",
            cls.FRENCH.value: "法语",
            cls.GERMAN.value: "德语",
            cls.JAPANESE.value: "日语",
            cls.KOREAN.value: "韩语",
            cls.RUSSIAN.value: "俄语",
            cls.SPANISH.value: "西班牙语",
            cls.THAI.value: "泰语",
            cls.ITALIAN.value: "意大利语",
            cls.PORTUGUESE.value: "葡萄牙语",
            cls.VIETNAMESE.value: "越南语",
            cls.ARABIC.value: "阿拉伯语",
            cls.TURKISH.value: "土耳其语",
            cls.HUNGARIAN.value: "匈牙利语"
        }


class STTOutputFormat(Enum):
    """STT输出格式选项"""
    SRT = "srt"
    JSON = "json"
    TEXT = "text"

    @classmethod
    def get_formats(cls):
        """获取所有输出格式选项"""
        return [fmt.value for fmt in cls]

    @classmethod
    def get_format_names(cls):
        """获取格式名称映射"""
        return {
            cls.SRT.value: "SRT字幕文件",
            cls.JSON.value: "JSON格式",
            cls.TEXT.value: "纯文本"
        }


class STTDevice(Enum):
    """STT设备选项"""
    CPU = "cpu"
    CUDA = "cuda"

    @classmethod
    def get_devices(cls):
        """获取所有设备选项"""
        return [device.value for device in cls]

    @classmethod
    def get_device_names(cls):
        """获取设备名称映射"""
        return {
            cls.CPU.value: "CPU",
            cls.CUDA.value: "CUDA (GPU)"
        }


class STTConfig:
    """STT配置类"""
    
    DEFAULT_CONFIG = {
        "stt_enabled": False,
        "stt_auto_process": False,
        "stt_model": STTModel.BASE.value,
        "stt_language": STTLanguage.AUTO.value,
        "stt_output_format": STTOutputFormat.SRT.value,
        "stt_device": STTDevice.CPU.value,
        "stt_model_path": "./stt-main/models",
        "stt_beam_size": 5,
        "stt_best_of": 5,
        "stt_temperature": 0,
        "stt_vad_filter": True,
        "stt_condition_on_previous_text": False,
        "stt_initial_prompt_zh": "转录为中文简体。"
    }
    
    @classmethod
    def get_default_config(cls):
        """获取默认配置"""
        return cls.DEFAULT_CONFIG.copy()
    
    @classmethod
    def validate_config(cls, config: dict) -> dict:
        """验证并修正配置"""
        validated_config = cls.get_default_config()
        
        for key, value in config.items():
            if key in validated_config:
                if key == "stt_model" and value not in STTModel.get_models():
                    validated_config[key] = STTModel.BASE.value
                elif key == "stt_language" and value not in STTLanguage.get_languages():
                    validated_config[key] = STTLanguage.AUTO.value
                elif key == "stt_output_format" and value not in STTOutputFormat.get_formats():
                    validated_config[key] = STTOutputFormat.SRT.value
                elif key == "stt_device" and value not in STTDevice.get_devices():
                    validated_config[key] = STTDevice.CPU.value
                elif key in ["stt_beam_size", "stt_best_of", "stt_temperature"]:
                    try:
                        validated_config[key] = int(value) if key != "stt_temperature" else float(value)
                    except (ValueError, TypeError):
                        pass
                elif key in ["stt_enabled", "stt_auto_process", "stt_vad_filter", "stt_condition_on_previous_text"]:
                    validated_config[key] = bool(value)
                else:
                    validated_config[key] = value
        
        return validated_config


class STTTask:
    """STT任务状态管理"""
    
    def __init__(self, task_id: str, file_path: str, config: dict):
        self.task_id = task_id
        self.file_path = file_path
        self.config = config
        self.status = "pending"  # pending, processing, completed, failed
        self.progress = 0.0
        self.message = ""
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
    
    def to_dict(self):
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "file_path": self.file_path,
            "config": self.config,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """从字典创建实例"""
        from datetime import datetime
        
        task = cls(data["task_id"], data["file_path"], data["config"])
        task.status = data.get("status", "pending")
        task.progress = data.get("progress", 0.0)
        task.message = data.get("message", "")
        task.result = data.get("result")
        task.error = data.get("error")
        
        if data.get("start_time"):
            task.start_time = datetime.fromisoformat(data["start_time"])
        if data.get("end_time"):
            task.end_time = datetime.fromisoformat(data["end_time"])
        
        return task