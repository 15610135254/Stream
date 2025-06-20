"""
录制预览对话框
提供录制前预览直播流的功能界面
"""

import flet as ft
import base64
from typing import Optional, Dict, Any

from ...utils.logger import logger


class PreviewDialog(ft.AlertDialog):
    """录制预览对话框"""
    
    def __init__(self, app, url: str = "", quality: str = "OD"):
        super().__init__()
        self.app = app
        self.url = url
        self.quality = quality
        self.preview_manager = getattr(app, 'preview_manager', None)
        self.current_preview_data = None
        
        # 初始化组件
        self.init_components()
        
        # 设置对话框属性
        self.modal = True
        self.title = ft.Text("录制预览", size=18, weight=ft.FontWeight.BOLD)
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
        self._.update(language.get("preview", {}))
        self._.update(language.get("base", {}))
    
    def init_components(self):
        """初始化UI组件"""
        # URL输入框
        self.url_input = ft.TextField(
            label="直播间URL",
            value=self.url,
            expand=True,
            on_change=self.on_url_change
        )
        
        # 质量选择
        self.quality_dropdown = ft.Dropdown(
            label="预览质量",
            options=[
                ft.dropdown.Option("OD", "原画"),
                ft.dropdown.Option("UHD", "超清"),
                ft.dropdown.Option("HD", "高清"),
                ft.dropdown.Option("SD", "标清"),
                ft.dropdown.Option("LD", "流畅")
            ],
            value=self.quality,
            width=120,
            on_change=self.on_quality_change
        )
        
        # 代理设置
        self.use_proxy_switch = ft.Switch(
            label="使用代理",
            value=False
        )
        
        # 获取预览按钮
        self.preview_button = ft.ElevatedButton(
            "获取预览",
            icon=ft.icons.PLAY_CIRCLE,
            on_click=self.on_get_preview,
            disabled=not self.url
        )
        
        # 刷新按钮
        self.refresh_button = ft.ElevatedButton(
            "刷新",
            icon=ft.icons.REFRESH,
            on_click=self.on_refresh_preview,
            disabled=True
        )
        
        # 进度指示器
        self.progress_ring = ft.ProgressRing(visible=False, width=30, height=30)
        self.status_text = ft.Text("", size=12, color=ft.colors.BLUE_GREY_600)
        
        # 预览信息区域
        self.preview_info_area = self.create_preview_info_area()
        
        # 预览截图区域
        self.screenshot_area = self.create_screenshot_area()
        
        # 音频测试区域
        self.audio_test_area = self.create_audio_test_area()
        
        # 选项卡
        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(text="基本信息", icon=ft.icons.INFO, content=self.preview_info_area),
                ft.Tab(text="视频预览", icon=ft.icons.VIDEO_CALL, content=self.screenshot_area),
                ft.Tab(text="音频测试", icon=ft.icons.AUDIOTRACK, content=self.audio_test_area),
            ]
        )
    
    def create_preview_info_area(self) -> ft.Container:
        """创建预览信息区域"""
        # 基本信息显示
        self.info_title = ft.Text("", size=16, weight=ft.FontWeight.BOLD)
        self.info_anchor = ft.Text("", size=14)
        self.info_platform = ft.Text("", size=14)
        self.info_status = ft.Text("", size=14)
        
        # 技术信息显示
        self.info_resolution = ft.Text("", size=12)
        self.info_bitrate = ft.Text("", size=12)
        self.info_audio = ft.Text("", size=12)
        
        # 可用质量列表
        self.quality_chips_row = ft.Row([], spacing=5, wrap=True)
        
        # 观看人数和开播时间
        self.info_viewers = ft.Text("", size=12)
        self.info_start_time = ft.Text("", size=12)
        
        return ft.Container(
            content=ft.Column([
                ft.Text("直播间信息", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.info_title,
                self.info_anchor,
                self.info_platform,
                self.info_status,
                
                ft.Container(height=10),
                ft.Text("技术参数", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.info_resolution,
                self.info_bitrate,
                self.info_audio,
                
                ft.Container(height=10),
                ft.Text("可用质量", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.quality_chips_row,
                
                ft.Container(height=10),
                ft.Text("其他信息", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.info_viewers,
                self.info_start_time,
                
            ], spacing=5, scroll=ft.ScrollMode.AUTO),
            padding=20
        )
    
    def create_screenshot_area(self) -> ft.Container:
        """创建截图预览区域"""
        # 截图显示
        self.screenshot_image = ft.Image(
            width=320,
            height=240,
            fit=ft.ImageFit.CONTAIN,
            border_radius=ft.border_radius.all(8)
        )
        
        # 截图按钮
        self.capture_button = ft.ElevatedButton(
            "捕获截图",
            icon=ft.icons.CAMERA_ALT,
            on_click=self.on_capture_screenshot,
            disabled=True
        )
        
        # 截图状态
        self.screenshot_status = ft.Text("", size=12)
        
        return ft.Container(
            content=ft.Column([
                ft.Text("视频预览截图", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                
                ft.Container(
                    content=self.screenshot_image,
                    alignment=ft.alignment.center,
                    border=ft.border.all(1, ft.colors.OUTLINE),
                    border_radius=ft.border_radius.all(8),
                    padding=10
                ),
                
                ft.Container(height=10),
                ft.Row([
                    self.capture_button,
                    ft.Container(expand=True),
                ]),
                self.screenshot_status,
                
                ft.Container(height=10),
                ft.Text(
                    "提示：截图预览可以帮助您确认直播内容和画质",
                    size=12,
                    color=ft.colors.BLUE_GREY_600
                )
                
            ], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20
        )
    
    def create_audio_test_area(self) -> ft.Container:
        """创建音频测试区域"""
        # 音频测试按钮
        self.audio_test_button = ft.ElevatedButton(
            "测试音频流",
            icon=ft.icons.VOLUME_UP,
            on_click=self.on_test_audio,
            disabled=True
        )
        
        # 音频信息显示
        self.audio_codec_text = ft.Text("", size=12)
        self.audio_bitrate_text = ft.Text("", size=12)
        self.audio_sample_rate_text = ft.Text("", size=12)
        self.audio_channels_text = ft.Text("", size=12)
        
        # 音频测试状态
        self.audio_test_status = ft.Text("", size=12)
        
        return ft.Container(
            content=ft.Column([
                ft.Text("音频流测试", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                
                ft.Row([
                    self.audio_test_button,
                    ft.Container(expand=True),
                ]),
                self.audio_test_status,
                
                ft.Container(height=10),
                ft.Text("音频参数", size=14, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                self.audio_codec_text,
                self.audio_bitrate_text,
                self.audio_sample_rate_text,
                self.audio_channels_text,
                
                ft.Container(height=10),
                ft.Text(
                    "提示：音频测试可以验证音频流的可用性和参数",
                    size=12,
                    color=ft.colors.BLUE_GREY_600
                )
                
            ], spacing=5),
            padding=20
        )
    
    def create_content(self) -> ft.Container:
        """创建对话框内容"""
        return ft.Container(
            width=600,
            height=550,
            content=ft.Column([
                # 输入区域
                ft.Row([
                    self.url_input,
                    self.quality_dropdown
                ], spacing=10),
                
                ft.Row([
                    self.use_proxy_switch,
                    ft.Container(expand=True),
                    self.preview_button,
                    self.refresh_button,
                    self.progress_ring
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                
                self.status_text,
                ft.Divider(),
                
                # 预览内容区域
                ft.Container(
                    content=self.tabs,
                    expand=True
                )
            ], spacing=10),
            padding=10
        )
    
    def create_actions(self) -> list:
        """创建对话框操作按钮"""
        return [
            ft.TextButton("关闭", on_click=self.on_close)
        ]
    
    def on_url_change(self, e):
        """URL变化事件"""
        self.url = e.control.value.strip()
        self.preview_button.disabled = not self.url
        self.preview_button.update()
        
        # 清除之前的预览数据
        self.clear_preview_data()
    
    def on_quality_change(self, e):
        """质量变化事件"""
        self.quality = e.control.value
        # 如果已有预览数据，刷新预览
        if self.current_preview_data:
            self.app.page.run_task(self.on_refresh_preview, None)
    
    async def on_get_preview(self, e):
        """获取预览信息"""
        if not self.url:
            await self.app.snack_bar.show_snack_bar("请输入直播间URL", bgcolor=ft.colors.RED)
            return
        
        if not self.preview_manager:
            await self.app.snack_bar.show_snack_bar("预览功能未初始化", bgcolor=ft.colors.RED)
            return
        
        self.show_loading("正在获取预览信息...")
        
        try:
            preview_data = await self.preview_manager.get_stream_preview(
                url=self.url,
                quality=self.quality,
                use_proxy=self.use_proxy_switch.value
            )
            
            if preview_data:
                self.current_preview_data = preview_data
                self.update_preview_display(preview_data)
                self.refresh_button.disabled = False
                self.refresh_button.update()
                
                self.capture_button.disabled = False
                self.capture_button.update()
                
                self.audio_test_button.disabled = False
                self.audio_test_button.update()
                
                self.status_text.value = "预览信息获取成功"
                self.status_text.color = ft.colors.GREEN
            else:
                self.status_text.value = "获取预览信息失败"
                self.status_text.color = ft.colors.RED
                
        except Exception as ex:
            logger.error(f"获取预览信息失败: {ex}")
            self.status_text.value = f"获取失败: {str(ex)}"
            self.status_text.color = ft.colors.RED
        
        finally:
            self.hide_loading()
    
    async def on_refresh_preview(self, e):
        """刷新预览信息"""
        if not self.url or not self.preview_manager:
            return
        
        self.show_loading("正在刷新预览信息...")
        
        try:
            preview_data = await self.preview_manager.refresh_preview(
                url=self.url,
                quality=self.quality
            )
            
            if preview_data:
                self.current_preview_data = preview_data
                self.update_preview_display(preview_data)
                self.status_text.value = "预览信息已刷新"
                self.status_text.color = ft.colors.GREEN
            else:
                self.status_text.value = "刷新预览信息失败"
                self.status_text.color = ft.colors.RED
                
        except Exception as ex:
            logger.error(f"刷新预览信息失败: {ex}")
            self.status_text.value = f"刷新失败: {str(ex)}"
            self.status_text.color = ft.colors.RED
        
        finally:
            self.hide_loading()
    
    async def on_capture_screenshot(self, e):
        """捕获预览截图"""
        if not self.url or not self.preview_manager:
            return
        
        self.capture_button.disabled = True
        self.capture_button.update()
        self.screenshot_status.value = "正在捕获截图..."
        self.screenshot_status.update()
        
        try:
            screenshot_data = await self.preview_manager.capture_preview_screenshot(
                url=self.url,
                quality=self.quality
            )
            
            if screenshot_data:
                # 将截图数据转换为base64并显示
                screenshot_base64 = base64.b64encode(screenshot_data).decode()
                self.screenshot_image.src_base64 = screenshot_base64
                self.screenshot_image.update()
                
                self.screenshot_status.value = "截图捕获成功"
                self.screenshot_status.color = ft.colors.GREEN
            else:
                self.screenshot_status.value = "截图捕获失败"
                self.screenshot_status.color = ft.colors.RED
                
        except Exception as ex:
            logger.error(f"捕获截图失败: {ex}")
            self.screenshot_status.value = f"捕获失败: {str(ex)}"
            self.screenshot_status.color = ft.colors.RED
        
        finally:
            self.capture_button.disabled = False
            self.capture_button.update()
            self.screenshot_status.update()
    
    async def on_test_audio(self, e):
        """测试音频流"""
        if not self.url or not self.preview_manager:
            return
        
        self.audio_test_button.disabled = True
        self.audio_test_button.update()
        self.audio_test_status.value = "正在测试音频流..."
        self.audio_test_status.update()
        
        try:
            audio_result = await self.preview_manager.test_audio_stream(
                url=self.url,
                quality=self.quality
            )
            
            if audio_result["success"]:
                # 显示音频信息
                self.audio_codec_text.value = f"编码格式: {audio_result.get('codec', '未知')}"
                self.audio_bitrate_text.value = f"码率: {audio_result.get('bitrate', '未知')}"
                self.audio_sample_rate_text.value = f"采样率: {audio_result.get('sample_rate', '未知')} Hz"
                self.audio_channels_text.value = f"声道数: {audio_result.get('channels', '未知')}"
                
                self.audio_codec_text.update()
                self.audio_bitrate_text.update()
                self.audio_sample_rate_text.update()
                self.audio_channels_text.update()
                
                self.audio_test_status.value = "音频测试成功"
                self.audio_test_status.color = ft.colors.GREEN
            else:
                self.audio_test_status.value = audio_result.get("message", "音频测试失败")
                self.audio_test_status.color = ft.colors.RED
                
        except Exception as ex:
            logger.error(f"音频测试失败: {ex}")
            self.audio_test_status.value = f"测试失败: {str(ex)}"
            self.audio_test_status.color = ft.colors.RED
        
        finally:
            self.audio_test_button.disabled = False
            self.audio_test_button.update()
            self.audio_test_status.update()
    
    def update_preview_display(self, preview_data):
        """更新预览显示"""
        # 基本信息
        self.info_title.value = f"标题: {preview_data.title}"
        self.info_anchor.value = f"主播: {preview_data.anchor_name}"
        self.info_platform.value = f"平台: {preview_data.platform}"
        self.info_status.value = f"状态: {'🔴 直播中' if preview_data.is_live else '⚫ 未开播'}"
        self.info_status.color = ft.colors.GREEN if preview_data.is_live else ft.colors.GREY
        
        # 技术信息
        self.info_resolution.value = f"分辨率: {preview_data.resolution or '未知'}"
        self.info_bitrate.value = f"码率: {preview_data.bitrate or '未知'}"
        self.info_audio.value = f"音频: {preview_data.audio_info or '未检测'}"
        
        # 可用质量
        self.quality_chips_row.controls.clear()
        for quality in preview_data.available_qualities:
            chip = ft.Chip(
                label=ft.Text(quality),
                selected=quality == preview_data.current_quality,
                on_select=lambda e, q=quality: self.on_quality_chip_select(q)
            )
            self.quality_chips_row.controls.append(chip)
        
        # 其他信息
        if preview_data.viewer_count is not None:
            self.info_viewers.value = f"观看人数: {preview_data.viewer_count}"
        else:
            self.info_viewers.value = "观看人数: 未知"
        
        if preview_data.start_time:
            self.info_start_time.value = f"开播时间: {preview_data.start_time}"
        else:
            self.info_start_time.value = "开播时间: 未知"
        
        # 更新所有控件
        self.info_title.update()
        self.info_anchor.update()
        self.info_platform.update()
        self.info_status.update()
        self.info_resolution.update()
        self.info_bitrate.update()
        self.info_audio.update()
        self.quality_chips_row.update()
        self.info_viewers.update()
        self.info_start_time.update()
    
    def on_quality_chip_select(self, quality: str):
        """质量标签选择事件"""
        self.quality_dropdown.value = quality
        self.quality_dropdown.update()
        self.quality = quality
        
        # 刷新预览
        self.app.page.run_task(self.on_refresh_preview, None)
    
    def clear_preview_data(self):
        """清除预览数据"""
        self.current_preview_data = None
        
        # 清除显示内容
        self.info_title.value = ""
        self.info_anchor.value = ""
        self.info_platform.value = ""
        self.info_status.value = ""
        self.info_resolution.value = ""
        self.info_bitrate.value = ""
        self.info_audio.value = ""
        self.quality_chips_row.controls.clear()
        self.info_viewers.value = ""
        self.info_start_time.value = ""
        
        # 清除截图
        self.screenshot_image.src_base64 = None
        
        # 清除音频信息
        self.audio_codec_text.value = ""
        self.audio_bitrate_text.value = ""
        self.audio_sample_rate_text.value = ""
        self.audio_channels_text.value = ""
        
        # 禁用按钮
        self.refresh_button.disabled = True
        self.capture_button.disabled = True
        self.audio_test_button.disabled = True
        
        # 清除状态
        self.status_text.value = ""
        self.screenshot_status.value = ""
        self.audio_test_status.value = ""
        
        # 更新界面
        self.update_all_controls()
    
    def update_all_controls(self):
        """更新所有控件"""
        controls_to_update = [
            self.info_title, self.info_anchor, self.info_platform, self.info_status,
            self.info_resolution, self.info_bitrate, self.info_audio,
            self.quality_chips_row, self.info_viewers, self.info_start_time,
            self.screenshot_image, self.audio_codec_text, self.audio_bitrate_text,
            self.audio_sample_rate_text, self.audio_channels_text,
            self.refresh_button, self.capture_button, self.audio_test_button,
            self.status_text, self.screenshot_status, self.audio_test_status
        ]
        
        for control in controls_to_update:
            try:
                control.update()
            except:
                pass  # 忽略更新错误
    
    def show_loading(self, message: str):
        """显示加载状态"""
        self.progress_ring.visible = True
        self.status_text.value = message
        self.status_text.color = ft.colors.BLUE
        self.preview_button.disabled = True
        
        self.progress_ring.update()
        self.status_text.update()
        self.preview_button.update()
    
    def hide_loading(self):
        """隐藏加载状态"""
        self.progress_ring.visible = False
        self.preview_button.disabled = False
        
        self.progress_ring.update()
        self.status_text.update()
        self.preview_button.update()
    
    def on_close(self, e):
        """关闭对话框"""
        # 清理预览缓存
        if self.preview_manager and self.url:
            self.preview_manager.clear_preview_cache(self.url)
        
        self.open = False
        self.update()