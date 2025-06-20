"""
录制预览管理器
负责处理录制前的预览功能
"""

import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from ..utils.logger import logger
from .platform_handlers import get_platform_handler, StreamData


@dataclass
class StreamPreviewData:
    """流预览数据"""
    url: str
    title: str
    anchor_name: str
    platform: str
    platform_key: str
    is_live: bool
    record_url: str
    available_qualities: List[str]
    current_quality: str
    resolution: Optional[str] = None
    bitrate: Optional[str] = None
    frame_rate: Optional[str] = None
    audio_info: Optional[str] = None
    thumbnail_url: Optional[str] = None
    viewer_count: Optional[int] = None
    start_time: Optional[str] = None
    preview_screenshot: Optional[bytes] = None


class PreviewManager:
    """录制预览管理器"""
    
    def __init__(self, app):
        self.app = app
        self.settings = app.settings
        self.user_config = self.settings.user_config
        self.account_config = self.settings.accounts_config
        self.active_previews: Dict[str, StreamPreviewData] = {}
        
    async def get_stream_preview(
        self, 
        url: str, 
        quality: str = "OD", 
        use_proxy: bool = False
    ) -> Optional[StreamPreviewData]:
        """获取流预览信息"""
        
        try:
            # 获取平台处理器
            proxy = None
            if use_proxy and self.user_config.get("enable_proxy"):
                proxy = self.user_config.get("proxy_address")
            
            # 获取平台信息
            from .platform_handlers import get_platform_info
            platform, platform_key = get_platform_info(url)
            
            if not platform or not platform_key:
                logger.error(f"不支持的平台URL: {url}")
                return None
            
            # 获取Cookie和账号信息
            cookies = self.settings.cookies_config.get(platform_key)
            username = self.account_config.get(platform_key, {}).get("username")
            password = self.account_config.get(platform_key, {}).get("password")
            account_type = self.account_config.get(platform_key, {}).get("account_type")
            
            # 创建平台处理器
            handler = get_platform_handler(
                live_url=url,
                proxy=proxy,
                cookies=cookies,
                record_quality=quality,
                platform=platform,
                username=username,
                password=password,
                account_type=account_type
            )
            
            # 获取流信息
            stream_info = await handler.get_stream_info(url)
            
            if not stream_info:
                logger.error(f"无法获取流信息: {url}")
                return None
            
            # 获取可用的录制质量列表
            available_qualities = await self._get_available_qualities(handler, url)
            
            # 创建预览数据
            preview_data = StreamPreviewData(
                url=url,
                title=stream_info.title or "无标题",
                anchor_name=stream_info.anchor_name or "未知主播",
                platform=platform,
                platform_key=platform_key,
                is_live=stream_info.is_live,
                record_url=stream_info.record_url or "",
                available_qualities=available_qualities,
                current_quality=quality,
                resolution=await self._get_resolution_info(stream_info.record_url),
                bitrate=await self._get_bitrate_info(stream_info.record_url),
                viewer_count=getattr(stream_info, 'viewer_count', None),
                start_time=getattr(stream_info, 'start_time', None),
                thumbnail_url=getattr(stream_info, 'thumbnail_url', None)
            )
            
            # 缓存预览数据
            self.active_previews[url] = preview_data
            
            logger.info(f"成功获取流预览信息: {url}")
            return preview_data
            
        except Exception as e:
            logger.error(f"获取流预览信息失败: {url}, 错误: {e}")
            return None
    
    async def _get_available_qualities(self, handler, url: str) -> List[str]:
        """获取可用的录制质量列表"""
        try:
            # 尝试获取不同质量的流信息
            qualities = ["OD", "UHD", "HD", "SD", "LD"]  # 从高到低
            available_qualities = []
            
            for quality in qualities:
                try:
                    # 创建新的处理器实例测试质量
                    test_handler = get_platform_handler(
                        live_url=url,
                        proxy=handler.proxy if hasattr(handler, 'proxy') else None,
                        cookies=handler.cookies if hasattr(handler, 'cookies') else None,
                        record_quality=quality,
                        platform=handler.platform if hasattr(handler, 'platform') else None
                    )
                    
                    stream_info = await test_handler.get_stream_info(url)
                    if stream_info and stream_info.record_url:
                        available_qualities.append(quality)
                        
                except Exception:
                    continue  # 忽略不支持的质量
            
            return available_qualities if available_qualities else ["OD"]
            
        except Exception as e:
            logger.error(f"获取可用质量列表失败: {e}")
            return ["OD"]  # 返回默认质量
    
    async def _get_resolution_info(self, record_url: str) -> Optional[str]:
        """获取流分辨率信息"""
        if not record_url:
            return None
            
        try:
            # 使用ffprobe获取流信息
            import subprocess
            
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                record_url
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=10
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and stdout:
                resolution = stdout.decode().strip()
                if 'x' in resolution:
                    return resolution
                    
        except Exception as e:
            logger.debug(f"获取分辨率信息失败: {e}")
        
        return None
    
    async def _get_bitrate_info(self, record_url: str) -> Optional[str]:
        """获取流码率信息"""
        if not record_url:
            return None
            
        try:
            # 使用ffprobe获取码率信息
            import subprocess
            
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=bit_rate",
                "-of", "csv=s=x:p=0",
                record_url
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=10
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and stdout:
                bitrate = stdout.decode().strip()
                if bitrate and bitrate.isdigit():
                    # 转换为更友好的格式
                    bitrate_kbps = int(bitrate) // 1000
                    return f"{bitrate_kbps} kbps"
                    
        except Exception as e:
            logger.debug(f"获取码率信息失败: {e}")
        
        return None
    
    async def capture_preview_screenshot(self, url: str, quality: str = "OD") -> Optional[bytes]:
        """捕获预览截图"""
        try:
            preview_data = self.active_previews.get(url)
            if not preview_data or not preview_data.record_url:
                preview_data = await self.get_stream_preview(url, quality)
                
            if not preview_data or not preview_data.record_url:
                return None
            
            # 使用ffmpeg捕获截图
            import subprocess
            import tempfile
            
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_path = temp_file.name
            
            cmd = [
                "ffmpeg",
                "-y",
                "-i", preview_data.record_url,
                "-vframes", "1",
                "-q:v", "2",
                "-s", "320x240",  # 小尺寸预览
                temp_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=15
            )
            
            await process.communicate()
            
            if process.returncode == 0:
                with open(temp_path, 'rb') as f:
                    screenshot_data = f.read()
                
                # 清理临时文件
                import os
                try:
                    os.unlink(temp_path)
                except:
                    pass
                
                # 缓存截图数据
                preview_data.preview_screenshot = screenshot_data
                
                logger.info(f"成功捕获预览截图: {url}")
                return screenshot_data
                
        except Exception as e:
            logger.error(f"捕获预览截图失败: {url}, 错误: {e}")
        
        return None
    
    async def test_audio_stream(self, url: str, quality: str = "OD") -> Dict[str, Any]:
        """测试音频流"""
        try:
            preview_data = self.active_previews.get(url)
            if not preview_data or not preview_data.record_url:
                preview_data = await self.get_stream_preview(url, quality)
                
            if not preview_data or not preview_data.record_url:
                return {"success": False, "message": "无法获取流信息"}
            
            # 使用ffprobe获取音频信息
            import subprocess
            
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name,bit_rate,sample_rate,channels",
                "-of", "json",
                preview_data.record_url
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=10
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and stdout:
                import json
                audio_info = json.loads(stdout.decode())
                
                if audio_info.get("streams"):
                    stream = audio_info["streams"][0]
                    audio_data = {
                        "success": True,
                        "codec": stream.get("codec_name", "unknown"),
                        "bitrate": stream.get("bit_rate", "unknown"),
                        "sample_rate": stream.get("sample_rate", "unknown"),
                        "channels": stream.get("channels", "unknown")
                    }
                    
                    # 更新预览数据
                    preview_data.audio_info = f"{audio_data['codec']} {audio_data['sample_rate']}Hz {audio_data['channels']}ch"
                    
                    logger.info(f"音频测试成功: {url}")
                    return audio_data
                    
        except Exception as e:
            logger.error(f"音频测试失败: {url}, 错误: {e}")
        
        return {"success": False, "message": "音频测试失败"}
    
    async def refresh_preview(self, url: str, quality: str = "OD") -> Optional[StreamPreviewData]:
        """刷新预览信息"""
        # 清除缓存
        if url in self.active_previews:
            del self.active_previews[url]
        
        # 重新获取预览信息
        return await self.get_stream_preview(url, quality)
    
    def get_cached_preview(self, url: str) -> Optional[StreamPreviewData]:
        """获取缓存的预览信息"""
        return self.active_previews.get(url)
    
    def clear_preview_cache(self, url: Optional[str] = None):
        """清除预览缓存"""
        if url:
            self.active_previews.pop(url, None)
        else:
            self.active_previews.clear()
    
    def get_preview_summary(self, url: str) -> Dict[str, Any]:
        """获取预览摘要信息"""
        preview_data = self.active_previews.get(url)
        if not preview_data:
            return {}
        
        return {
            "title": preview_data.title,
            "anchor_name": preview_data.anchor_name,
            "platform": preview_data.platform,
            "is_live": preview_data.is_live,
            "resolution": preview_data.resolution,
            "bitrate": preview_data.bitrate,
            "audio_info": preview_data.audio_info,
            "available_qualities": preview_data.available_qualities,
            "viewer_count": preview_data.viewer_count,
            "has_screenshot": preview_data.preview_screenshot is not None
        }