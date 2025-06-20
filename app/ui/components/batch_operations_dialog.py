"""
批量操作对话框
提供批量导入/导出、批量设置等功能的UI界面
"""

import flet as ft
import os
from typing import List, Dict, Any, Optional

from ...models.recording_model import Recording
from ...utils.logger import logger


class BatchOperationsDialog(ft.AlertDialog):
    """批量操作对话框"""
    
    def __init__(self, app, recordings: List[Recording] = None):
        super().__init__()
        self.app = app
        self.recordings = recordings or []
        self.batch_manager = getattr(app, 'batch_operations_manager', None)
        
        # 初始化组件
        self.init_components()
        
        # 设置对话框属性
        self.modal = True
        self.title = ft.Text("批量操作", size=18, weight=ft.FontWeight.BOLD)
        self.content = self.create_content()
        self.actions = self.create_actions()
        self.actions_alignment = ft.MainAxisAlignment.END
        
        # 语言支持
        self.app.language_manager.add_observer(self)
        self._ = {}
        self.load_language()
    
    def load_language(self):
        """加载语言文本"""
        language = self.app.language_manager.language
        self._.update(language.get("batch_operations", {}))
        self._.update(language.get("base", {}))
    
    def init_components(self):
        """初始化UI组件"""
        # 选项卡
        self.tab_bar = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(text="导入/导出", icon=ft.icons.IMPORT_EXPORT),
                ft.Tab(text="批量设置", icon=ft.icons.SETTINGS),
                ft.Tab(text="其他操作", icon=ft.icons.MORE_HORIZ),
            ],
            on_change=self.on_tab_change
        )
        
        # 导入/导出页面组件
        self.import_export_content = self.create_import_export_content()
        
        # 批量设置页面组件
        self.batch_settings_content = self.create_batch_settings_content()
        
        # 其他操作页面组件
        self.other_operations_content = self.create_other_operations_content()
        
        # 当前显示的内容
        self.current_content = self.import_export_content
        
        # 进度指示器
        self.progress_bar = ft.ProgressBar(visible=False)
        self.progress_text = ft.Text("", visible=False, size=12)
    
    def create_import_export_content(self) -> ft.Container:
        """创建导入/导出页面内容"""
        
        # 导入部分
        self.import_file_path = ft.TextField(
            label="选择要导入的文件",
            hint_text="支持JSON和CSV格式",
            expand=True,
            read_only=True
        )
        
        import_file_button = ft.ElevatedButton(
            "浏览文件",
            icon=ft.icons.FOLDER_OPEN,
            on_click=self.on_select_import_file
        )
        
        import_button = ft.ElevatedButton(
            "开始导入",
            icon=ft.icons.UPLOAD,
            on_click=self.on_import_recordings,
            disabled=True
        )
        
        # 导出部分
        self.export_format = ft.Dropdown(
            label="导出格式",
            options=[
                ft.dropdown.Option("json", "JSON格式"),
                ft.dropdown.Option("csv", "CSV格式")
            ],
            value="json",
            width=150
        )
        
        export_button = ft.ElevatedButton(
            "导出选中任务",
            icon=ft.icons.DOWNLOAD,
            on_click=self.on_export_recordings,
            disabled=len(self.recordings) == 0
        )
        
        self.import_button = import_button
        self.export_button = export_button
        
        # 统计信息
        stats_text = f"当前选中 {len(self.recordings)} 个录制任务"
        if self.recordings:
            monitoring_count = sum(1 for rec in self.recordings if rec.monitor_status)
            stats_text += f"，其中 {monitoring_count} 个正在监控"
        
        stats_info = ft.Text(stats_text, size=12, color=ft.colors.BLUE_GREY_600)
        
        return ft.Container(
            content=ft.Column([
                # 导入部分
                ft.Text("导入录制任务", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Row([
                    self.import_file_path,
                    import_file_button
                ], spacing=10),
                ft.Row([import_button], alignment=ft.MainAxisAlignment.END),
                
                ft.Container(height=20),
                
                # 导出部分
                ft.Text("导出录制任务", size=16, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                stats_info,
                ft.Row([
                    self.export_format,
                    ft.Container(expand=True),
                    export_button
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                
            ], spacing=10),
            padding=20
        )
    
    def create_batch_settings_content(self) -> ft.Container:
        """创建批量设置页面内容"""
        
        # 录制格式设置
        self.format_dropdown = ft.Dropdown(
            label="录制格式",
            options=[
                ft.dropdown.Option("TS", "TS"),
                ft.dropdown.Option("MP4", "MP4"),
                ft.dropdown.Option("FLV", "FLV"),
                ft.dropdown.Option("MKV", "MKV"),
                ft.dropdown.Option("MOV", "MOV")
            ],
            width=120
        )
        
        # 录制质量设置
        self.quality_dropdown = ft.Dropdown(
            label="录制质量",
            options=[
                ft.dropdown.Option("OD", "原画"),
                ft.dropdown.Option("UHD", "超清"),
                ft.dropdown.Option("HD", "高清"),
                ft.dropdown.Option("SD", "标清"),
                ft.dropdown.Option("LD", "流畅")
            ],
            width=120
        )
        
        # 分段录制设置
        self.segment_switch = ft.Switch(label="启用分段录制", value=False)
        self.segment_time = ft.TextField(
            label="分段时长(秒)",
            value="1800",
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        # 定时录制设置
        self.scheduled_switch = ft.Switch(label="启用定时录制", value=False)
        self.scheduled_time = ft.TextField(
            label="开始时间 (HH:MM:SS)",
            hint_text="18:30:00",
            width=150
        )
        self.monitor_hours = ft.TextField(
            label="监控时长(小时)",
            value="5",
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        
        # 录制目录设置
        self.recording_dir = ft.TextField(
            label="录制目录",
            hint_text="留空使用默认目录",
            expand=True
        )
        
        dir_button = ft.ElevatedButton(
            "选择目录",
            icon=ft.icons.FOLDER,
            on_click=self.on_select_directory
        )
        
        # 消息推送设置
        self.message_push_switch = ft.Switch(label="启用消息推送", value=False)
        
        # 应用设置按钮
        apply_settings_button = ft.ElevatedButton(
            "应用设置到选中任务",
            icon=ft.icons.SAVE,
            on_click=self.on_apply_batch_settings,
            disabled=len(self.recordings) == 0
        )
        
        self.apply_settings_button = apply_settings_button
        
        # 设置项说明
        settings_info = ft.Text(
            f"将对 {len(self.recordings)} 个选中的录制任务应用以下设置：",
            size=12,
            color=ft.colors.BLUE_GREY_600
        )
        
        return ft.Container(
            content=ft.Column([
                settings_info,
                ft.Divider(),
                
                # 基本设置
                ft.Text("基本录制设置", size=14, weight=ft.FontWeight.BOLD),
                ft.Row([self.format_dropdown, self.quality_dropdown], spacing=20),
                
                ft.Container(height=10),
                
                # 分段设置
                ft.Text("分段录制设置", size=14, weight=ft.FontWeight.BOLD),
                self.segment_switch,
                self.segment_time,
                
                ft.Container(height=10),
                
                # 定时设置
                ft.Text("定时录制设置", size=14, weight=ft.FontWeight.BOLD),
                self.scheduled_switch,
                ft.Row([self.scheduled_time, self.monitor_hours], spacing=20),
                
                ft.Container(height=10),
                
                # 目录设置
                ft.Text("录制目录设置", size=14, weight=ft.FontWeight.BOLD),
                ft.Row([self.recording_dir, dir_button], spacing=10),
                
                ft.Container(height=10),
                
                # 其他设置
                ft.Text("其他设置", size=14, weight=ft.FontWeight.BOLD),
                self.message_push_switch,
                
                ft.Container(height=20),
                ft.Row([apply_settings_button], alignment=ft.MainAxisAlignment.END)
                
            ], spacing=5, scroll=ft.ScrollMode.AUTO),
            padding=20
        )
    
    def create_other_operations_content(self) -> ft.Container:
        """创建其他操作页面内容"""
        
        # 复制任务
        copy_button = ft.ElevatedButton(
            "复制选中任务",
            icon=ft.icons.CONTENT_COPY,
            on_click=self.on_copy_recordings,
            disabled=len(self.recordings) == 0
        )
        
        # 统计信息
        stats_button = ft.ElevatedButton(
            "查看统计信息",
            icon=ft.icons.ANALYTICS,
            on_click=self.on_show_statistics
        )
        
        # 操作说明
        operations_info = [
            "• 复制任务：创建选中任务的副本，副本默认不启动监控",
            "• 统计信息：显示选中任务的详细统计数据",
        ]
        
        info_text = ft.Column([
            ft.Text(info, size=12) for info in operations_info
        ])
        
        return ft.Container(
            content=ft.Column([
                ft.Text(f"选中了 {len(self.recordings)} 个录制任务", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                
                ft.Text("可用操作", size=14, weight=ft.FontWeight.BOLD),
                ft.Row([copy_button, stats_button], spacing=20),
                
                ft.Container(height=20),
                ft.Text("操作说明", size=14, weight=ft.FontWeight.BOLD),
                info_text,
                
            ], spacing=10),
            padding=20
        )
    
    def create_content(self) -> ft.Container:
        """创建对话框内容"""
        return ft.Container(
            width=600,
            height=500,
            content=ft.Column([
                self.tab_bar,
                ft.Container(
                    content=self.current_content,
                    expand=True
                ),
                self.progress_bar,
                self.progress_text
            ]),
        )
    
    def create_actions(self) -> List[ft.Control]:
        """创建对话框操作按钮"""
        return [
            ft.TextButton("关闭", on_click=self.on_close)
        ]
    
    def on_tab_change(self, e):
        """标签页切换事件"""
        selected_index = e.control.selected_index
        
        if selected_index == 0:
            self.current_content = self.import_export_content
        elif selected_index == 1:
            self.current_content = self.batch_settings_content
        else:
            self.current_content = self.other_operations_content
        
        # 更新显示内容
        self.content.content.controls[1].content = self.current_content
        self.content.update()
    
    async def on_select_import_file(self, e):
        """选择导入文件"""
        file_picker = ft.FilePicker(on_result=self.on_import_file_result)
        self.app.page.overlay.append(file_picker)
        self.app.page.update()
        
        await file_picker.pick_files(
            dialog_title="选择要导入的文件",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json", "csv"]
        )
    
    def on_import_file_result(self, e: ft.FilePickerResultEvent):
        """导入文件选择结果"""
        if e.files:
            file_path = e.files[0].path
            self.import_file_path.value = file_path
            self.import_button.disabled = False
            self.import_file_path.update()
            self.import_button.update()
    
    async def on_export_recordings(self, e):
        """导出录制任务"""
        if not self.recordings:
            await self.app.snack_bar.show_snack_bar("没有选中的录制任务", bgcolor=ft.colors.RED)
            return
        
        file_picker = ft.FilePicker(on_result=self.on_export_file_result)
        self.app.page.overlay.append(file_picker)
        self.app.page.update()
        
        # 根据格式设置文件扩展名
        format_type = self.export_format.value
        extension = "json" if format_type == "json" else "csv"
        
        await file_picker.save_file(
            dialog_title="保存导出文件",
            file_name=f"recordings_export_{len(self.recordings)}_{format_type}.{extension}",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=[extension]
        )
    
    async def on_export_file_result(self, e: ft.FilePickerResultEvent):
        """导出文件保存结果"""
        if e.path:
            self.show_progress("正在导出录制任务...")
            
            try:
                format_type = self.export_format.value
                if format_type == "json":
                    success = await self.batch_manager.export_recordings_to_json(self.recordings, e.path)
                else:
                    success = await self.batch_manager.export_recordings_to_csv(self.recordings, e.path)
                
                if success:
                    await self.app.snack_bar.show_snack_bar(
                        f"成功导出 {len(self.recordings)} 个录制任务", 
                        bgcolor=ft.colors.GREEN
                    )
                else:
                    await self.app.snack_bar.show_snack_bar("导出失败", bgcolor=ft.colors.RED)
                    
            except Exception as ex:
                logger.error(f"导出录制任务失败: {ex}")
                await self.app.snack_bar.show_snack_bar(f"导出失败: {str(ex)}", bgcolor=ft.colors.RED)
            
            finally:
                self.hide_progress()
    
    async def on_import_recordings(self, e):
        """导入录制任务"""
        file_path = self.import_file_path.value
        if not file_path or not os.path.exists(file_path):
            await self.app.snack_bar.show_snack_bar("请选择有效的导入文件", bgcolor=ft.colors.RED)
            return
        
        self.show_progress("正在导入录制任务...")
        
        try:
            if file_path.endswith('.json'):
                result = await self.batch_manager.import_recordings_from_json(file_path)
            else:
                result = await self.batch_manager.import_recordings_from_csv(file_path)
            
            if result["success"]:
                message = result["message"]
                await self.app.snack_bar.show_snack_bar(message, bgcolor=ft.colors.GREEN)
                
                # 刷新主页面
                if hasattr(self.app, 'current_page') and hasattr(self.app.current_page, 'refresh_cards_on_click'):
                    await self.app.current_page.refresh_cards_on_click(None)
            else:
                await self.app.snack_bar.show_snack_bar(result["message"], bgcolor=ft.colors.RED)
                
        except Exception as ex:
            logger.error(f"导入录制任务失败: {ex}")
            await self.app.snack_bar.show_snack_bar(f"导入失败: {str(ex)}", bgcolor=ft.colors.RED)
        
        finally:
            self.hide_progress()
    
    async def on_select_directory(self, e):
        """选择录制目录"""
        directory_picker = ft.FilePicker(on_result=self.on_directory_result)
        self.app.page.overlay.append(directory_picker)
        self.app.page.update()
        
        await directory_picker.get_directory_path(dialog_title="选择录制目录")
    
    def on_directory_result(self, e: ft.FilePickerResultEvent):
        """目录选择结果"""
        if e.path:
            self.recording_dir.value = e.path
            self.recording_dir.update()
    
    async def on_apply_batch_settings(self, e):
        """应用批量设置"""
        if not self.recordings:
            await self.app.snack_bar.show_snack_bar("没有选中的录制任务", bgcolor=ft.colors.RED)
            return
        
        self.show_progress("正在应用批量设置...")
        
        try:
            # 收集设置
            settings = {}
            
            if self.format_dropdown.value:
                settings["record_format"] = self.format_dropdown.value
            
            if self.quality_dropdown.value:
                settings["quality"] = self.quality_dropdown.value
            
            settings["segment_record"] = self.segment_switch.value
            
            if self.segment_time.value:
                settings["segment_time"] = self.segment_time.value
            
            settings["scheduled_recording"] = self.scheduled_switch.value
            
            if self.scheduled_time.value:
                settings["scheduled_start_time"] = self.scheduled_time.value
            
            if self.monitor_hours.value:
                settings["monitor_hours"] = self.monitor_hours.value
            
            if self.recording_dir.value:
                settings["recording_dir"] = self.recording_dir.value
            
            settings["enabled_message_push"] = self.message_push_switch.value
            
            # 应用设置
            updated_count = await self.batch_manager.batch_update_settings(self.recordings, settings)
            
            if updated_count > 0:
                await self.app.snack_bar.show_snack_bar(
                    f"成功更新 {updated_count} 个录制任务的设置", 
                    bgcolor=ft.colors.GREEN
                )
                
                # 刷新卡片显示
                for recording in self.recordings:
                    await self.app.record_card_manager.update_card(recording)
            else:
                await self.app.snack_bar.show_snack_bar("更新设置失败", bgcolor=ft.colors.RED)
                
        except Exception as ex:
            logger.error(f"应用批量设置失败: {ex}")
            await self.app.snack_bar.show_snack_bar(f"更新失败: {str(ex)}", bgcolor=ft.colors.RED)
        
        finally:
            self.hide_progress()
    
    async def on_copy_recordings(self, e):
        """复制录制任务"""
        if not self.recordings:
            await self.app.snack_bar.show_snack_bar("没有选中的录制任务", bgcolor=ft.colors.RED)
            return
        
        self.show_progress("正在复制录制任务...")
        
        try:
            copied_recordings = await self.batch_manager.batch_copy_recordings(self.recordings)
            
            if copied_recordings:
                await self.app.snack_bar.show_snack_bar(
                    f"成功复制 {len(copied_recordings)} 个录制任务", 
                    bgcolor=ft.colors.GREEN
                )
                
                # 刷新主页面
                if hasattr(self.app, 'current_page') and hasattr(self.app.current_page, 'refresh_cards_on_click'):
                    await self.app.current_page.refresh_cards_on_click(None)
            else:
                await self.app.snack_bar.show_snack_bar("复制任务失败", bgcolor=ft.colors.RED)
                
        except Exception as ex:
            logger.error(f"复制录制任务失败: {ex}")
            await self.app.snack_bar.show_snack_bar(f"复制失败: {str(ex)}", bgcolor=ft.colors.RED)
        
        finally:
            self.hide_progress()
    
    async def on_show_statistics(self, e):
        """显示统计信息"""
        if not self.batch_manager:
            await self.app.snack_bar.show_snack_bar("批量操作功能未初始化", bgcolor=ft.colors.RED)
            return
        
        stats = self.batch_manager.get_batch_operation_statistics(self.recordings)
        
        if not stats:
            await self.app.snack_bar.show_snack_bar("没有统计数据", bgcolor=ft.colors.ORANGE)
            return
        
        # 创建统计信息对话框
        stats_dialog = self.create_statistics_dialog(stats)
        stats_dialog.open = True
        self.app.dialog_area.content = stats_dialog
        self.app.dialog_area.update()
    
    def create_statistics_dialog(self, stats: Dict[str, Any]) -> ft.AlertDialog:
        """创建统计信息对话框"""
        # 平台分布
        platforms_text = []
        for platform, count in stats["platforms"].items():
            platforms_text.append(f"• {platform}: {count} 个")
        
        # 格式分布
        formats_text = []
        for format_type, count in stats["formats"].items():
            formats_text.append(f"• {format_type}: {count} 个")
        
        # 质量分布
        qualities_text = []
        for quality, count in stats["qualities"].items():
            qualities_text.append(f"• {quality}: {count} 个")
        
        content = ft.Column([
            ft.Text("录制任务统计信息", size=16, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            
            ft.Text(f"总任务数: {stats['total_count']} 个", size=14),
            ft.Text(f"监控中: {stats['monitoring_count']} 个", size=14),
            ft.Text(f"录制中: {stats['recording_count']} 个", size=14),
            
            ft.Container(height=10),
            ft.Text("平台分布:", size=14, weight=ft.FontWeight.BOLD),
            *[ft.Text(text, size=12) for text in platforms_text],
            
            ft.Container(height=10),
            ft.Text("格式分布:", size=14, weight=ft.FontWeight.BOLD),
            *[ft.Text(text, size=12) for text in formats_text],
            
            ft.Container(height=10),
            ft.Text("质量分布:", size=14, weight=ft.FontWeight.BOLD),
            *[ft.Text(text, size=12) for text in qualities_text],
        ], scroll=ft.ScrollMode.AUTO)
        
        return ft.AlertDialog(
            title=ft.Text("统计信息"),
            content=ft.Container(content=content, width=400, height=400),
            actions=[
                ft.TextButton("关闭", on_click=lambda e: self.close_stats_dialog())
            ]
        )
    
    def close_stats_dialog(self):
        """关闭统计对话框"""
        self.app.dialog_area.content.open = False
        self.app.dialog_area.update()
    
    def show_progress(self, message: str):
        """显示进度"""
        self.progress_bar.visible = True
        self.progress_text.visible = True
        self.progress_text.value = message
        self.progress_bar.update()
        self.progress_text.update()
    
    def hide_progress(self):
        """隐藏进度"""
        self.progress_bar.visible = False
        self.progress_text.visible = False
        self.progress_bar.update()
        self.progress_text.update()
    
    def on_close(self, e):
        """关闭对话框"""
        self.open = False
        self.update()