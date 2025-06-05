"""
定时推送设置标签页组件

提供定时任务配置、状态显示和控制按钮的UI组件
"""

import gradio as gr
from src.ui.ui_constants import CSS_CLASSES

def create_scheduler_tab():
    """
    创建定时推送设置标签页
    
    包含定时任务配置、状态显示和控制按钮
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("⏰ 定时推送设置", id=6):
        with gr.Group(elem_classes=[CSS_CLASSES["CONTROL_PANEL"]]):
            with gr.Row():
                with gr.Column():
                    # 基本设置
                    scheduler_enabled = gr.Checkbox(
                        label="启用定时推送", 
                        value=False,
                        info="启用后将按设定间隔自动执行任务"
                    )
                    scheduler_interval = gr.Slider(
                        label="推送间隔（小时）", 
                        minimum=0.1, 
                        maximum=24, 
                        step=0.1, 
                        value=1, 
                        info="任务执行间隔时间，小数点表示小时分数"
                    )
                    scheduler_task = gr.Textbox(
                        label="定时任务内容", 
                        lines=4, 
                        value="搜索最新的人工智能技术发展趋势，特别关注大型语言模型和生成式AI的应用",
                        info="研究任务内容描述"
                    )
                
                with gr.Column():
                    # 高级设置
                    scheduler_title = gr.Textbox(
                        label="推送标题前缀", 
                        value="深度研究",
                        info="消息标题前缀，将与任务内容拼接"
                    )
                    with gr.Row():
                        scheduler_iterations = gr.Number(
                            label="最大搜索迭代次数", 
                            value=2, 
                            minimum=1, 
                            maximum=5, 
                            step=1, 
                            precision=0,
                            info="每次任务执行的最大搜索迭代次数"
                        )
                        scheduler_queries = gr.Number(
                            label="每迭代查询数", 
                            value=3, 
                            minimum=1, 
                            maximum=5, 
                            step=1, 
                            precision=0,
                            info="每次迭代的最大查询数量"
                        )
            
            # 状态展示和操作按钮
            with gr.Row():
                with gr.Column():
                    scheduler_status_text = gr.Markdown("调度器状态: 未启动")
                    scheduler_next_run_text = gr.Markdown("下次执行时间: 无排程")
                with gr.Column():
                    with gr.Row():
                        scheduler_start_btn = gr.Button("✔️ 启动调度器", variant="primary")
                        scheduler_stop_btn = gr.Button("⛔ 停止调度器", variant="stop")
                        scheduler_run_once_btn = gr.Button("▶️ 立即执行一次", variant="secondary")
            
            # 执行结果显示
            scheduler_result_text = gr.Markdown("最新执行结果将在这里显示...")
    
    return (scheduler_enabled, scheduler_interval, scheduler_task, scheduler_title,
            scheduler_iterations, scheduler_queries, scheduler_status_text,
            scheduler_next_run_text, scheduler_start_btn, scheduler_stop_btn,
            scheduler_run_once_btn, scheduler_result_text)
