"""
UI配置标签页组件

提供主题选择、界面设置、字体设置等UI配置选项
"""

import gradio as gr
from src.ui.ui_constants import CSS_CLASSES, THEME_MAP, DEFAULT_THEME

def create_config_tab():
    """
    创建UI配置标签页
    
    包含主题选择、界面设置、字体大小等配置选项
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("🎨 UI配置", id=8):
        with gr.Group(elem_classes=[CSS_CLASSES["THEME_SECTION"]]):
            with gr.Row():
                with gr.Column(scale=2):
                    theme_selector = gr.Dropdown(
                        choices=list(THEME_MAP.keys()),
                        value=DEFAULT_THEME,
                        label="界面主题",
                        info="选择界面主题风格",
                        interactive=True
                    )
                    ui_refresh_btn = gr.Button("🔄 应用主题", variant="primary")
                
                with gr.Column(scale=1):
                    dark_mode = gr.Checkbox(
                        label="深色模式", 
                        value=False,
                        info="启用深色模式（需要应用主题）",
                        interactive=True
                    )
            
            with gr.Accordion("高级UI设置", open=False):
                with gr.Row():
                    font_size = gr.Slider(
                        minimum=12,
                        maximum=20,
                        value=14,
                        step=1,
                        label="基础字体大小",
                        info="调整界面文本大小（单位：像素）"
                    )
                    
                    border_radius = gr.Slider(
                        minimum=0,
                        maximum=16,
                        value=8,
                        step=1,
                        label="边框圆角",
                        info="调整UI元素的圆角半径（单位：像素）"
                    )
                
                with gr.Row():
                    control_width = gr.Slider(
                        minimum=30,
                        maximum=70,
                        value=40,
                        step=5,
                        label="控制面板宽度 (%)",
                        info="调整左侧控制面板占比"
                    )
                    
                    content_width = gr.Slider(
                        minimum=30,
                        maximum=70,
                        value=60,
                        step=5,
                        label="内容区域宽度 (%)",
                        info="调整右侧内容区域占比"
                    )
            
            with gr.Accordion("自定义CSS", open=False):
                custom_css = gr.Textbox(
                    label="自定义CSS",
                    lines=8,
                    placeholder="/* 在此处添加自定义CSS样式 */\n.header-text h1 {\n  color: blue;\n}",
                    info="添加自定义CSS样式（高级用户）"
                )
                apply_css_btn = gr.Button("应用自定义CSS", variant="secondary")
            
            with gr.Row():
                reset_ui_btn = gr.Button("↩️ 重置为默认值", variant="secondary")
                save_ui_btn = gr.Button("💾 保存配置", variant="primary")
            
            ui_status_text = gr.Markdown("UI配置状态: 未修改")
    
    # 主题相关的函数
    def update_theme_preview(theme_name):
        theme_info = f"已选择主题: {theme_name}"
        return theme_info
    
    # 绑定主题选择器的变更事件
    theme_selector.change(
        fn=update_theme_preview,
        inputs=theme_selector,
        outputs=ui_status_text
    )
    
    return (theme_selector, ui_refresh_btn, dark_mode, font_size, border_radius,
            control_width, content_width, custom_css, apply_css_btn,
            reset_ui_btn, save_ui_btn, ui_status_text)
