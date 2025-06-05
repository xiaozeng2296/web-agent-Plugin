"""
浏览器设置标签页组件

提供浏览器类型、窗口大小、录制选项等设置的UI组件
"""

import gradio as gr
from src.ui.ui_constants import CSS_CLASSES

def create_browser_settings_tab():
    """
    创建浏览器设置标签页
    
    包含浏览器类型、窗口大小、录制选项等设置选项
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("🌐 浏览器设置", id=3):
        with gr.Group(elem_classes=[CSS_CLASSES["THEME_SECTION"]]):
            with gr.Row():
                use_own_browser = gr.Checkbox(
                    label="使用自己的浏览器",
                    value=True,
                    info="使用您现有的浏览器实例",
                    interactive=True
                )
                keep_browser_open = gr.Checkbox(
                    label="保持浏览器开启",
                    value=False,
                    info="在任务之间保持浏览器开启",
                    interactive=True
                )
                headless = gr.Checkbox(
                    label="无头模式",
                    value=False,
                    info="在无GUI模式下运行浏览器",
                    interactive=True
                )
                disable_security = gr.Checkbox(
                    label="禁用安全特性",
                    value=True,
                    info="禁用浏览器安全特性",
                    interactive=True
                )
                enable_recording = gr.Checkbox(
                    label="启用录制",
                    value=True,
                    info="启用保存浏览器录制",
                    interactive=True
                )

            with gr.Row():
                window_w = gr.Number(
                    label="窗口宽度",
                    value=1280,
                    info="浏览器窗口宽度",
                    interactive=True
                )
                window_h = gr.Number(
                    label="窗口高度",
                    value=1100,
                    info="浏览器窗口高度",
                    interactive=True
                )

            chrome_cdp = gr.Textbox(
                label="CDP URL",
                placeholder="http://localhost:9222",
                value="",
                info="用于Google远程调试的CDP",
                interactive=True,
            )

            save_recording_path = gr.Textbox(
                label="录制路径",
                placeholder="例如 ./tmp/record_videos",
                value="./tmp/record_videos",
                info="保存浏览器录制的路径",
                interactive=True,
            )

            save_trace_path = gr.Textbox(
                label="Trace路径",
                placeholder="例如 ./tmp/traces",
                value="./tmp/traces",
                info="保存Agent跟踪信息的路径",
                interactive=True,
            )

            save_agent_history_path = gr.Textbox(
                label="Agent历史保存路径",
                placeholder="例如 ./tmp/agent_history",
                value="./tmp/agent_history",
                info="指定保存Agent历史记录的目录",
                interactive=True,
            )
            
    # 添加联动事件，启用/禁用录制时更新路径输入框可交互性
    enable_recording.change(
        lambda enabled: gr.update(interactive=enabled),
        inputs=enable_recording,
        outputs=save_recording_path
    )
    
    return (use_own_browser, keep_browser_open, headless, disable_security, enable_recording, 
            window_w, window_h, chrome_cdp, save_recording_path, save_trace_path, save_agent_history_path)
