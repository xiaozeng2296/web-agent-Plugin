"""
录像管理标签页组件

提供录像列表、预览和下载功能的UI组件
"""

import gradio as gr
import os
from src.ui.ui_constants import CSS_CLASSES

def create_recordings_tab():
    """
    创建录像管理标签页
    
    包含录像文件列表、预览窗口和操作按钮
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("📹 录像", id=7):
        with gr.Group(elem_classes=[CSS_CLASSES["CONTROL_PANEL"]]):
            recordings_path = gr.Textbox(
                label="录像存储路径",
                value="./tmp/record_videos",
                info="存储录像文件的本地路径"
            )
            
            with gr.Row():
                recordings_refresh_btn = gr.Button("🔄 刷新录像列表", variant="primary")
                recordings_clear_btn = gr.Button("🗑️ 清除所有录像", variant="stop")
            
            with gr.Row():
                with gr.Column(scale=1):
                    recordings_list = gr.Dropdown(
                        label="选择录像",
                        choices=[],
                        value=None,
                        interactive=True,
                        info="可用的录像文件列表"
                    )
                
                with gr.Column(scale=1):
                    with gr.Row():
                        recordings_open_btn = gr.Button("🎬 预览所选录像", variant="secondary")
                        recordings_delete_btn = gr.Button("🗑️ 删除所选录像", variant="stop")
            
            # 录像预览
            recordings_preview = gr.Image(label="录像预览", format="gif", type="filepath")
            
            # 下载和详细信息
            with gr.Row():
                recordings_download_btn = gr.Button("⬇️ 下载所选录像", variant="primary")
                recordings_info_text = gr.Markdown("选择录像以查看详情...")
            
            # 下载组件
            recordings_download = gr.File(label="下载录像文件", visible=False)
    
    # 函数：刷新录像列表
    def refresh_recordings_list(path):
        """
        刷新录像文件列表
        
        参数:
            path: 录像存储路径
            
        返回:
            list: 录像文件列表
        """
        try:
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                return [], "创建录像目录: " + path
            
            recordings = [f for f in os.listdir(path) if f.endswith(('.gif', '.mp4', '.webm'))]
            return sorted(recordings, reverse=True), f"找到 {len(recordings)} 个录像文件"
        except Exception as e:
            return [], f"读取录像目录时出错: {str(e)}"
    
    # 绑定刷新按钮事件
    recordings_refresh_btn.click(
        fn=lambda path: refresh_recordings_list(path)[0],
        inputs=recordings_path,
        outputs=recordings_list
    )
            
    return (recordings_path, recordings_refresh_btn, recordings_clear_btn, recordings_list,
            recordings_open_btn, recordings_delete_btn, recordings_preview,
            recordings_download_btn, recordings_info_text, recordings_download)
