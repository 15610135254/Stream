"""
批量操作管理器
负责处理录制任务的批量操作功能
"""

import csv
import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..models.recording_model import Recording
from ..utils.logger import logger
from ..core.platform_handlers import get_platform_info


class BatchOperationsManager:
    """批量操作管理器"""
    
    def __init__(self, app):
        self.app = app
        self.record_manager = app.record_manager
        self.config_manager = app.config_manager
        self.settings = app.settings
        
    async def export_recordings_to_json(self, recordings: List[Recording], file_path: str) -> bool:
        """导出录制任务到JSON文件"""
        try:
            export_data = {
                "export_time": datetime.now().isoformat(),
                "export_version": "1.0",
                "total_count": len(recordings),
                "recordings": [recording.to_dict() for recording in recordings]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"成功导出 {len(recordings)} 个录制任务到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出录制任务失败: {e}")
            return False
    
    async def export_recordings_to_csv(self, recordings: List[Recording], file_path: str) -> bool:
        """导出录制任务到CSV文件"""
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # 写入表头
                headers = [
                    '录制ID', 'URL地址', '主播名称', '录制格式', '录制质量',
                    '分段录制', '分段时长', '监控状态', '定时录制', '定时开始时间',
                    '监控时长', '录制目录', '消息推送', '平台', '平台标识'
                ]
                writer.writerow(headers)
                
                # 写入数据
                for recording in recordings:
                    row = [
                        recording.rec_id,
                        recording.url,
                        recording.streamer_name,
                        recording.record_format,
                        recording.quality,
                        recording.segment_record,
                        recording.segment_time,
                        recording.monitor_status,
                        recording.scheduled_recording,
                        recording.scheduled_start_time,
                        recording.monitor_hours,
                        recording.recording_dir,
                        recording.enabled_message_push,
                        recording.platform,
                        recording.platform_key
                    ]
                    writer.writerow(row)
            
            logger.info(f"成功导出 {len(recordings)} 个录制任务到CSV: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出录制任务到CSV失败: {e}")
            return False
    
    async def import_recordings_from_json(self, file_path: str) -> Dict[str, Any]:
        """从JSON文件导入录制任务"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            recordings_data = data.get("recordings", [])
            if not recordings_data:
                return {"success": False, "message": "文件中没有找到录制任务数据"}
            
            imported_recordings = []
            skipped_urls = []
            existing_urls = {rec.url for rec in self.record_manager.recordings}
            
            for rec_data in recordings_data:
                url = rec_data.get("url")
                if not url:
                    continue
                    
                # 检查URL是否已存在
                if url in existing_urls:
                    skipped_urls.append(url)
                    continue
                
                # 创建新的录制任务
                new_recording = self._create_recording_from_data(rec_data)
                imported_recordings.append(new_recording)
                existing_urls.add(url)
            
            # 批量添加录制任务
            for recording in imported_recordings:
                await self.record_manager.add_recording(recording)
            
            result_message = f"成功导入 {len(imported_recordings)} 个录制任务"
            if skipped_urls:
                result_message += f"，跳过 {len(skipped_urls)} 个重复URL"
            
            logger.info(result_message)
            return {
                "success": True,
                "imported_count": len(imported_recordings),
                "skipped_count": len(skipped_urls),
                "message": result_message
            }
            
        except Exception as e:
            logger.error(f"从JSON导入录制任务失败: {e}")
            return {"success": False, "message": f"导入失败: {str(e)}"}
    
    async def import_recordings_from_csv(self, file_path: str) -> Dict[str, Any]:
        """从CSV文件导入录制任务"""
        try:
            imported_recordings = []
            skipped_urls = []
            existing_urls = {rec.url for rec in self.record_manager.recordings}
            
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    url = row.get("URL地址", "").strip()
                    if not url:
                        continue
                    
                    # 检查URL是否已存在
                    if url in existing_urls:
                        skipped_urls.append(url)
                        continue
                    
                    # 从CSV行创建录制任务数据
                    rec_data = {
                        "url": url,
                        "streamer_name": row.get("主播名称", "").strip() or "直播间",
                        "record_format": row.get("录制格式", "TS"),
                        "quality": row.get("录制质量", "OD"),
                        "segment_record": row.get("分段录制", "False").lower() == "true",
                        "segment_time": row.get("分段时长", "1800"),
                        "monitor_status": row.get("监控状态", "True").lower() == "true",
                        "scheduled_recording": row.get("定时录制", "False").lower() == "true",
                        "scheduled_start_time": row.get("定时开始时间", ""),
                        "monitor_hours": row.get("监控时长", ""),
                        "recording_dir": row.get("录制目录", ""),
                        "enabled_message_push": row.get("消息推送", "False").lower() == "true"
                    }
                    
                    new_recording = self._create_recording_from_data(rec_data)
                    imported_recordings.append(new_recording)
                    existing_urls.add(url)
            
            # 批量添加录制任务
            for recording in imported_recordings:
                await self.record_manager.add_recording(recording)
            
            result_message = f"成功导入 {len(imported_recordings)} 个录制任务"
            if skipped_urls:
                result_message += f"，跳过 {len(skipped_urls)} 个重复URL"
            
            logger.info(result_message)
            return {
                "success": True,
                "imported_count": len(imported_recordings),
                "skipped_count": len(skipped_urls),
                "message": result_message
            }
            
        except Exception as e:
            logger.error(f"从CSV导入录制任务失败: {e}")
            return {"success": False, "message": f"导入失败: {str(e)}"}
    
    def _create_recording_from_data(self, rec_data: Dict[str, Any]) -> Recording:
        """从数据字典创建Recording对象"""
        # 生成新的录制ID
        rec_id = str(uuid.uuid4())
        
        # 创建Recording对象
        recording = Recording(
            rec_id=rec_id,
            url=rec_data.get("url", ""),
            streamer_name=rec_data.get("streamer_name", "直播间"),
            record_format=rec_data.get("record_format", "TS"),
            quality=rec_data.get("quality", "OD"),
            segment_record=rec_data.get("segment_record", False),
            segment_time=rec_data.get("segment_time", "1800"),
            monitor_status=rec_data.get("monitor_status", True),
            scheduled_recording=rec_data.get("scheduled_recording", False),
            scheduled_start_time=rec_data.get("scheduled_start_time", ""),
            monitor_hours=rec_data.get("monitor_hours", ""),
            recording_dir=rec_data.get("recording_dir", ""),
            enabled_message_push=rec_data.get("enabled_message_push", False)
        )
        
        # 获取平台信息
        platform, platform_key = get_platform_info(recording.url)
        if platform and platform_key:
            recording.platform = platform
            recording.platform_key = platform_key
        
        # 设置循环时间
        recording.loop_time_seconds = int(self.settings.user_config.get("loop_time_seconds", 300))
        
        return recording
    
    async def batch_update_settings(self, recordings: List[Recording], settings: Dict[str, Any]) -> int:
        """批量更新录制设置"""
        updated_count = 0
        
        try:
            for recording in recordings:
                # 更新录制设置
                if "record_format" in settings:
                    recording.record_format = settings["record_format"]
                
                if "quality" in settings:
                    recording.quality = settings["quality"]
                
                if "segment_record" in settings:
                    recording.segment_record = settings["segment_record"]
                
                if "segment_time" in settings:
                    recording.segment_time = settings["segment_time"]
                
                if "scheduled_recording" in settings:
                    recording.scheduled_recording = settings["scheduled_recording"]
                
                if "scheduled_start_time" in settings:
                    recording.scheduled_start_time = settings["scheduled_start_time"]
                
                if "monitor_hours" in settings:
                    recording.monitor_hours = settings["monitor_hours"]
                
                if "recording_dir" in settings:
                    recording.recording_dir = settings["recording_dir"]
                
                if "enabled_message_push" in settings:
                    recording.enabled_message_push = settings["enabled_message_push"]
                
                updated_count += 1
            
            # 保存更改
            await self.record_manager.persist_recordings()
            
            logger.info(f"批量更新了 {updated_count} 个录制任务的设置")
            return updated_count
            
        except Exception as e:
            logger.error(f"批量更新设置失败: {e}")
            return 0
    
    async def batch_copy_recordings(self, recordings: List[Recording]) -> List[Recording]:
        """批量复制录制任务"""
        copied_recordings = []
        
        try:
            for recording in recordings:
                # 创建副本
                new_rec_data = recording.to_dict()
                new_rec_data["rec_id"] = str(uuid.uuid4())
                new_rec_data["streamer_name"] = f"{recording.streamer_name} (副本)"
                new_rec_data["monitor_status"] = False  # 副本默认不监控
                
                new_recording = Recording.from_dict(new_rec_data)
                new_recording.loop_time_seconds = int(self.settings.user_config.get("loop_time_seconds", 300))
                
                await self.record_manager.add_recording(new_recording)
                copied_recordings.append(new_recording)
            
            logger.info(f"成功复制了 {len(copied_recordings)} 个录制任务")
            return copied_recordings
            
        except Exception as e:
            logger.error(f"批量复制录制任务失败: {e}")
            return []
    
    async def batch_set_recording_directory(self, recordings: List[Recording], directory: str) -> int:
        """批量设置录制目录"""
        updated_count = 0
        
        try:
            # 验证目录是否存在，不存在则创建
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            for recording in recordings:
                recording.recording_dir = directory
                updated_count += 1
            
            # 保存更改
            await self.record_manager.persist_recordings()
            
            logger.info(f"批量设置了 {updated_count} 个录制任务的录制目录: {directory}")
            return updated_count
            
        except Exception as e:
            logger.error(f"批量设置录制目录失败: {e}")
            return 0
    
    def get_batch_operation_statistics(self, recordings: List[Recording]) -> Dict[str, Any]:
        """获取批量操作的统计信息"""
        if not recordings:
            return {}
        
        stats = {
            "total_count": len(recordings),
            "monitoring_count": sum(1 for rec in recordings if rec.monitor_status),
            "recording_count": sum(1 for rec in recordings if rec.is_recording),
            "platforms": {},
            "formats": {},
            "qualities": {}
        }
        
        # 统计平台分布
        for recording in recordings:
            platform = recording.platform or "未知"
            stats["platforms"][platform] = stats["platforms"].get(platform, 0) + 1
        
        # 统计格式分布
        for recording in recordings:
            format_type = recording.record_format
            stats["formats"][format_type] = stats["formats"].get(format_type, 0) + 1
        
        # 统计质量分布
        for recording in recordings:
            quality = recording.quality
            stats["qualities"][quality] = stats["qualities"].get(quality, 0) + 1
        
        return stats