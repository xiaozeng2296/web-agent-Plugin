"""
Agent设置标签页组件

提供Agent类型、运行步数、视觉功能等设置的UI组件
"""

import gradio as gr
from src.ui.ui_constants import CSS_CLASSES

def create_agent_settings_tab():
    """
    创建Agent设置标签页
    
    包含Agent类型、最大步数、每步最大动作数、视觉功能等设置选项
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("⚙️ Agent设置", id=1):
        with gr.Group(elem_classes=[CSS_CLASSES["THEME_SECTION"]]):
            agent_type = gr.Radio(
                ["org", "custom"],
                label="Agent类型",
                value="custom",
                info="选择要使用的Agent类型",
                interactive=True
            )
            with gr.Column():
                max_steps = gr.Slider(
                    minimum=1,
                    maximum=200,
                    value=100,
                    step=1,
                    label="最大运行步数",
                    info="Agent将执行的最大步数",
                    interactive=True
                )
                max_actions_per_step = gr.Slider(
                    minimum=1,
                    maximum=100,
                    value=10,
                    step=1,
                    label="每步最大动作数",
                    info="Agent每步将执行的最大动作数",
                    interactive=True
                )
            with gr.Column():
                use_vision = gr.Checkbox(
                    label="使用视觉功能",
                    value=True,
                    info="启用视觉处理能力",
                    interactive=True
                )
                max_input_tokens = gr.Number(
                    label="最大输入令牌数",
                    value=5120000,
                    precision=0,
                    interactive=True
                )
                tool_calling_method = gr.Dropdown(
                    label="工具调用方法",
                    value="auto",
                    interactive=True,
                    allow_custom_value=True,
                    choices=["auto", "json_schema", "function_calling"],
                    info="工具调用函数名称",
                    visible=False
                )
                
    return agent_type, max_steps, max_actions_per_step, use_vision, max_input_tokens, tool_calling_method
