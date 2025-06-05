"""
运行Agent标签页组件

提供任务输入、执行按钮以及结果展示的UI组件
"""

import gradio as gr
from src.ui.ui_constants import CSS_CLASSES

def create_run_agent_tab():
    """
    创建运行Agent标签页
    
    包含任务描述输入、额外信息、执行按钮和结果展示区域
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("🤖 运行Agent", id=4):
        with gr.Group(elem_classes=[CSS_CLASSES["CONTROL_PANEL"]]):
            task = gr.Textbox(
                label="任务描述",
                lines=4,
                placeholder="在此输入您的任务...",
                value="访问 google.com 并搜索 'OpenAI'，点击搜索并提供第一个URL",
                info="描述您希望Agent执行的任务",
                interactive=True
            )
            add_infos = gr.Textbox(
                label="附加信息",
                lines=3,
                placeholder="添加任何有用的上下文或指示...",
                info="可选的提示，帮助LLM完成任务",
                value="",
                interactive=True
            )

            with gr.Row():
                run_button = gr.Button("▶️ 运行Agent", variant="primary", scale=2)
                stop_button = gr.Button("⏹️ 停止", variant="stop", scale=1)

        with gr.Group(elem_classes=[CSS_CLASSES["BROWSER_VIEW"]]):
            browser_view = gr.HTML(
                value="<h1 style='text-align:center; padding:40px;'>等待浏览器会话启动...</h1>",
                label="浏览器实时视图",
                visible=False
            )

        with gr.Group(elem_classes=[CSS_CLASSES["RESULTS_AREA"]]):
            gr.Markdown("### 结果", elem_classes=["results-header"])
            with gr.Row():
                with gr.Column():
                    final_result_output = gr.Textbox(
                        label="最终结果", lines=3, show_label=True
                    )
                with gr.Column():
                    errors_output = gr.Textbox(
                        label="错误", lines=3, show_label=True
                    )
            with gr.Row():
                with gr.Column():
                    model_actions_output = gr.Textbox(
                        label="模型动作", lines=3, show_label=True, visible=False
                    )
                with gr.Column():
                    model_thoughts_output = gr.Textbox(
                        label="模型思考", lines=3, show_label=True, visible=False
                    )
            recording_gif = gr.Image(label="结果GIF", format="gif")
            trace_file = gr.File(label="跟踪文件")
            agent_history_file = gr.File(label="Agent历史")
    
    return (task, add_infos, run_button, stop_button, browser_view,
            final_result_output, errors_output, model_actions_output,
            model_thoughts_output, recording_gif, trace_file, agent_history_file)
