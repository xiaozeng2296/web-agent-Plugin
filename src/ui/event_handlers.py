"""
UI事件处理模块

集中管理WebUI的事件处理逻辑，连接UI组件与业务功能
"""

import gradio as gr
import asyncio
import logging
from typing import Dict, Any, List, Tuple, Optional, Callable

from src.utils.app_state import app_state
from src.utils.utils import update_model_dropdown, get_latest_files

# 导入原始webui模块中的业务逻辑函数
# 后续这些函数将被逐步重构到对应模块中
from webui import (
    run_with_stream, stop_agent, stop_research_agent,
    run_deep_search, start_scheduler, stop_scheduler,
    run_push_task_once, close_global_browser
)

logger = logging.getLogger(__name__)

# ===== Agent设置标签页事件处理 =====
def register_agent_tab_events(agent_components: Tuple):
    """
    注册Agent设置标签页的事件处理器
    
    参数:
        agent_components: Agent设置标签页组件元组
    """
    agent_type, max_steps, max_actions_per_step, use_vision, max_input_tokens, tool_calling_method = agent_components
    
    # 根据Agent类型切换工具调用方法可见性
    def update_tool_calling_method_visibility(agent_type_value):
        """根据Agent类型更新工具调用方法可见性"""
        return gr.update(visible=agent_type_value == "org")
    
    agent_type.change(
        fn=update_tool_calling_method_visibility,
        inputs=agent_type,
        outputs=tool_calling_method
    )


# ===== LLM设置标签页事件处理 =====
def register_llm_tab_events(llm_components: Tuple):
    """
    注册LLM设置标签页的事件处理器
    
    参数:
        llm_components: LLM设置标签页组件元组
    """
    llm_provider, llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key = llm_components
    
    # 根据LLM提供商更新模型下拉列表
    llm_provider.change(
        fn=update_model_dropdown,
        inputs=llm_provider,
        outputs=llm_model_name
    )
    
    # 更新上下文长度滑块可见性
    def update_llm_num_ctx_visibility(provider):
        """更新上下文长度滑块可见性"""
        return gr.update(visible=provider == "ollama")
        
    llm_provider.change(
        fn=update_llm_num_ctx_visibility,
        inputs=llm_provider,
        outputs=ollama_num_ctx
    )


# ===== 浏览器设置标签页事件处理 =====
def register_browser_tab_events(browser_components: Tuple):
    """
    注册浏览器设置标签页的事件处理器
    
    参数:
        browser_components: 浏览器设置标签页组件元组
    """
    use_own_browser, keep_browser_open, headless, disable_security, enable_recording, window_w, window_h, chrome_cdp, save_recording_path, save_trace_path, save_agent_history_path = browser_components
    
    # 启用/禁用录制时更新路径输入框可交互性
    enable_recording.change(
        lambda enabled: gr.update(interactive=enabled),
        inputs=enable_recording,
        outputs=save_recording_path
    )


# ===== 运行Agent标签页事件处理 =====
def register_run_agent_tab_events(run_agent_components: Tuple, agent_components: Tuple, 
                               llm_components: Tuple, browser_components: Tuple):
    """
    注册运行Agent标签页的事件处理器
    
    参数:
        run_agent_components: 运行Agent标签页组件元组
        agent_components: Agent设置标签页组件元组
        llm_components: LLM设置标签页组件元组
        browser_components: 浏览器设置标签页组件元组
    """
    # 提取运行Agent组件
    task, add_infos, run_button, stop_button, browser_view, final_result_output, errors_output, model_actions_output, model_thoughts_output, recording_gif, trace_file, agent_history_file = run_agent_components
    
    # 提取Agent设置组件
    agent_type, max_steps, max_actions_per_step, use_vision, max_input_tokens, tool_calling_method = agent_components
    
    # 提取LLM设置组件
    llm_provider, llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key = llm_components
    
    # 提取浏览器设置组件
    use_own_browser, keep_browser_open, headless, disable_security, enable_recording, window_w, window_h, chrome_cdp, save_recording_path, save_trace_path, save_agent_history_path = browser_components
    
    # 运行按钮点击事件
    run_button.click(
        fn=run_with_stream,
        inputs=[
            agent_type, llm_provider, llm_model_name, ollama_num_ctx,
            llm_temperature, llm_base_url, llm_api_key,
            use_own_browser, keep_browser_open, headless, disable_security,
            window_w, window_h, save_recording_path, save_agent_history_path,
            save_trace_path, enable_recording, task, add_infos,
            max_steps, use_vision, max_actions_per_step,
            tool_calling_method, chrome_cdp, max_input_tokens
        ],
        outputs=[
            browser_view, final_result_output, errors_output,
            model_actions_output, model_thoughts_output,
            recording_gif, trace_file, agent_history_file
        ]
    )
    
    # 停止按钮点击事件
    stop_button.click(
        fn=stop_agent,
        inputs=[],
        outputs=[browser_view, final_result_output, errors_output]
    )


# ===== 深度研究标签页事件处理 =====
def register_research_tab_events(research_components: Tuple, llm_components: Tuple, 
                              browser_components: Tuple, agent_components: Tuple = None):
    """
    注册深度研究标签页的事件处理器
    
    参数:
        research_components: 深度研究标签页组件元组
        llm_components: LLM设置标签页组件元组
        browser_components: 浏览器设置标签页组件元组
    """
    # 提取研究组件
    research_task_input, max_search_iteration_input, max_query_per_iter_input, research_button, stop_research_button, markdown_output_display, markdown_download = research_components
    
    # 提取LLM设置组件
    llm_provider, llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key = llm_components
    
    # 提取浏览器设置组件
    use_own_browser, keep_browser_open, headless, disable_security, enable_recording, window_w, window_h, chrome_cdp, save_recording_path, save_trace_path, save_agent_history_path = browser_components
    
    # 获取use_vision变量，如果agent_components为None，则使用默认值False
    use_vision = agent_components[3] if agent_components else False
    
    # 研究按钮点击事件
    research_button.click(
        fn=run_deep_search,
        inputs=[
            research_task_input, max_search_iteration_input, max_query_per_iter_input,
            llm_provider, llm_model_name, ollama_num_ctx, llm_temperature,
            llm_base_url, llm_api_key, use_vision, use_own_browser,
            headless, chrome_cdp
        ],
        outputs=[markdown_output_display, markdown_download]
    )
    
    # 停止研究按钮点击事件
    stop_research_button.click(
        fn=stop_research_agent,
        inputs=[],
        outputs=[]
    )


# ===== 定时推送设置标签页事件处理 =====
def register_scheduler_tab_events(scheduler_components: Tuple):
    """
    注册定时推送设置标签页的事件处理器
    
    参数:
        scheduler_components: 定时推送设置标签页组件元组
    """
    # 提取调度器组件
    (scheduler_enabled, scheduler_interval, scheduler_task, scheduler_title,
     scheduler_iterations, scheduler_queries, scheduler_status_text,
     scheduler_next_run_text, scheduler_start_btn, scheduler_stop_btn,
     scheduler_run_once_btn, scheduler_result_text) = scheduler_components
    
    # 启动调度器按钮点击事件
    scheduler_start_btn.click(
        fn=start_scheduler,
        inputs=[
            scheduler_task, scheduler_interval, scheduler_title,
            scheduler_iterations, scheduler_queries
        ],
        outputs=[scheduler_status_text, scheduler_next_run_text]
    )
    
    # 停止调度器按钮点击事件
    scheduler_stop_btn.click(
        fn=stop_scheduler,
        inputs=[],
        outputs=[scheduler_status_text, scheduler_next_run_text]
    )
    
    # 立即执行一次按钮点击事件
    scheduler_run_once_btn.click(
        fn=run_push_task_once,
        inputs=[
            scheduler_task, scheduler_title,
            scheduler_iterations, scheduler_queries
        ],
        outputs=[scheduler_result_text, scheduler_status_text, scheduler_next_run_text]
    )


# ===== 录像标签页事件处理 =====
def register_recordings_tab_events(recordings_components: Tuple):
    """
    注册录像标签页的事件处理器
    
    参数:
        recordings_components: 录像标签页组件元组
    """
    # 提取录像组件
    (recordings_path, recordings_refresh_btn, recordings_clear_btn, recordings_list,
     recordings_open_btn, recordings_delete_btn, recordings_preview,
     recordings_download_btn, recordings_info_text, recordings_download) = recordings_components
    
    # 刷新录像列表函数
    def refresh_recordings_list(path):
        """刷新录像文件列表"""
        try:
            import os
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
                return [], "创建录像目录: " + path
            
            recordings = [f for f in os.listdir(path) if f.endswith(('.gif', '.mp4', '.webm'))]
            return sorted(recordings, reverse=True), f"找到 {len(recordings)} 个录像文件"
        except Exception as e:
            return [], f"读取录像目录时出错: {str(e)}"
    
    # 刷新录像列表按钮事件
    recordings_refresh_btn.click(
        fn=lambda path: refresh_recordings_list(path)[0],
        inputs=recordings_path,
        outputs=recordings_list
    )
    
    # 刷新录像信息
    recordings_refresh_btn.click(
        fn=lambda path: refresh_recordings_list(path)[1],
        inputs=recordings_path,
        outputs=recordings_info_text
    )
    
    # 预览录像文件
    def preview_recording(rec_path, selected_file):
        """预览所选录像文件"""
        if not selected_file:
            return None, "请先选择一个录像文件"
        
        try:
            import os
            full_path = os.path.join(rec_path, selected_file)
            if not os.path.exists(full_path):
                return None, f"文件不存在: {full_path}"
                
            return full_path, f"预览录像: {selected_file}"
        except Exception as e:
            return None, f"预览录像时出错: {str(e)}"
    
    # 预览按钮事件
    recordings_open_btn.click(
        fn=preview_recording,
        inputs=[recordings_path, recordings_list],
        outputs=[recordings_preview, recordings_info_text]
    )
    
    # 删除录像文件
    def delete_recording(rec_path, selected_file):
        """删除所选录像文件"""
        if not selected_file:
            return [], "请先选择一个录像文件"
        
        try:
            import os
            full_path = os.path.join(rec_path, selected_file)
            if not os.path.exists(full_path):
                return [], f"文件不存在: {full_path}"
                
            os.remove(full_path)
            recordings = [f for f in os.listdir(rec_path) if f.endswith(('.gif', '.mp4', '.webm'))]
            return sorted(recordings, reverse=True), f"已删除: {selected_file}"
        except Exception as e:
            return [], f"删除录像时出错: {str(e)}"
    
    # 删除按钮事件
    recordings_delete_btn.click(
        fn=delete_recording,
        inputs=[recordings_path, recordings_list],
        outputs=[recordings_list, recordings_info_text]
    )


# ===== UI配置标签页事件处理 =====
def register_config_tab_events(config_components: Tuple):
    """
    注册UI配置标签页的事件处理器
    
    参数:
        config_components: UI配置标签页组件元组
    """
    # 提取UI配置组件
    (theme_selector, ui_refresh_btn, dark_mode, font_size, border_radius,
     control_width, content_width, custom_css, apply_css_btn,
     reset_ui_btn, save_ui_btn, ui_status_text) = config_components
    
    # 主题相关的函数
    def update_theme_preview(theme_name):
        """更新主题预览信息"""
        theme_info = f"已选择主题: {theme_name}"
        return theme_info
    
    # 绑定主题选择器的变更事件
    theme_selector.change(
        fn=update_theme_preview,
        inputs=theme_selector,
        outputs=ui_status_text
    )
    
    # 应用主题按钮点击事件 - 由于Gradio限制，实际实现需要刷新页面，这里仅提示
    ui_refresh_btn.click(
        fn=lambda: "主题将在页面刷新后应用",
        inputs=[],
        outputs=ui_status_text
    )


# ===== 全局事件注册函数 =====
def register_all_events(demo: gr.Blocks, components: Dict[str, Tuple]):
    """
    注册所有UI事件处理器
    
    参数:
        demo: Gradio Blocks实例
        components: 各标签页组件字典
    """
    # 注册各标签页事件处理器
    register_agent_tab_events(components["agent"])
    register_llm_tab_events(components["llm"])
    register_browser_tab_events(components["browser"])
    register_run_agent_tab_events(
        components["run_agent"], 
        components["agent"], 
        components["llm"], 
        components["browser"]
    )
    register_research_tab_events(
        components["research"], 
        components["llm"], 
        components["browser"],
        components["agent"]
    )
    register_scheduler_tab_events(components["scheduler"])
    register_recordings_tab_events(components["recordings"])
    register_config_tab_events(components["config"])
    
    # 注册页面加载事件 - 更新浏览器视图
    demo.load(
        fn=lambda: gr.update(visible=app_state.get_browser_context() is not None),
        outputs=components["run_agent"][4]  # browser_view
    )
