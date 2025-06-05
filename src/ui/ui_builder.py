"""
UI构建器模块

负责整合和组装所有UI组件，创建完整的WebUI界面
"""

import gradio as gr

from src.ui.agent_tab import create_agent_settings_tab
from src.ui.browser_tab import create_browser_settings_tab
from src.ui.config_tab import create_config_tab
from src.ui.event_handlers import register_all_events
from src.ui.llm_tab import create_llm_settings_tab
from src.ui.recordings_tab import create_recordings_tab
from src.ui.research_tab import create_deep_research_tab
from src.ui.run_agent_tab import create_run_agent_tab
from src.ui.scheduler_tab import create_scheduler_tab
from src.ui.ui_constants import BASE_CSS, CSS_CLASSES
from src.ui.ui_utils import get_enhanced_css, apply_theme


def create_ui(css_mode="enhanced", title="Web Agent", subtitle="AI浏览器代理", theme_name="Ocean"):
    """
    创建完整的WebUI界面
    
    参数:
        css_mode: CSS样式模式 ("basic"或"enhanced")
        title: 页面标题
        subtitle: 页面副标题
        theme_name: 主题名称
        
    返回:
        Gradio界面实例
    """
    # 根据css_mode选择CSS样式
    css_content = get_enhanced_css() if css_mode == "enhanced" else BASE_CSS
    
    # 应用指定的主题
    theme = apply_theme(theme_name)
    
    with gr.Blocks(theme=theme, css=css_content) as demo:
        # 界面标题
        with gr.Row(elem_classes=[CSS_CLASSES["HEADER"]]):
            gr.Markdown(f"# {title}")
            gr.Markdown(f"### {subtitle}")
        
        # 创建标签页容器
        with gr.Tabs() as tabs:
            # 创建各个标签页并获取组件
            agent_components = create_agent_settings_tab()
            llm_components = create_llm_settings_tab()
            browser_components = create_browser_settings_tab()
            run_agent_components = create_run_agent_tab()
            research_components = create_deep_research_tab()
            scheduler_components = create_scheduler_tab()
            recordings_components = create_recordings_tab()
            config_components = create_config_tab()
            
            # 提取关键组件变量以便事件绑定
            # Agent设置组件
            agent_type, max_steps, max_actions_per_step, use_vision, max_input_tokens, tool_calling_method = agent_components
            
            # LLM设置组件
            llm_provider, llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key = llm_components
            
            # 浏览器设置组件
            use_own_browser, keep_browser_open, headless, disable_security, enable_recording, window_w, window_h, chrome_cdp, save_recording_path, save_trace_path, save_agent_history_path = browser_components
            
            # 运行Agent组件
            task, add_infos, run_button, stop_button, browser_view, final_result_output, errors_output, model_actions_output, model_thoughts_output, recording_gif, trace_file, agent_history_file = run_agent_components
            
            # 研究组件
            research_task_input, max_search_iteration_input, max_query_per_iter_input, research_button, stop_research_button, markdown_output_display, markdown_download = research_components
            
            # 调度器组件
            scheduler_enabled, scheduler_interval, scheduler_task, scheduler_title, scheduler_iterations, scheduler_queries, scheduler_status_text, scheduler_next_run_text, scheduler_start_btn, scheduler_stop_btn, scheduler_run_once_btn, scheduler_result_text = scheduler_components
            
            # 录像组件
            recordings_path, recordings_refresh_btn, recordings_clear_btn, recordings_list, recordings_open_btn, recordings_delete_btn, recordings_preview, recordings_download_btn, recordings_info_text, recordings_download = recordings_components
            
            # UI配置组件
            theme_selector, ui_refresh_btn, dark_mode, font_size, border_radius, control_width, content_width, custom_css, apply_css_btn, reset_ui_btn, save_ui_btn, ui_status_text = config_components
        
        # 收集所有组件，用于事件绑定
        components = {
            "agent": (
                agent_type, max_steps, max_actions_per_step, 
                use_vision, max_input_tokens, tool_calling_method
            ),
            "llm": (
                llm_provider, llm_model_name, ollama_num_ctx,
                llm_temperature, llm_base_url, llm_api_key
            ),
            "browser": (
                use_own_browser, keep_browser_open, headless, 
                disable_security, enable_recording, window_w, 
                window_h, chrome_cdp, save_recording_path, 
                save_trace_path, save_agent_history_path
            ),
            "run_agent": (
                task, add_infos, run_button, stop_button, 
                browser_view, final_result_output, errors_output, 
                model_actions_output, model_thoughts_output, 
                recording_gif, trace_file, agent_history_file
            ),
            "research": (
                research_task_input, max_search_iteration_input, 
                max_query_per_iter_input, research_button, 
                stop_research_button, markdown_output_display, 
                markdown_download
            ),
            "scheduler": (
                scheduler_enabled, scheduler_interval, scheduler_task, 
                scheduler_title, scheduler_iterations, scheduler_queries, 
                scheduler_status_text, scheduler_next_run_text, 
                scheduler_start_btn, scheduler_stop_btn, 
                scheduler_run_once_btn, scheduler_result_text
            ),
            "recordings": (
                recordings_path, recordings_refresh_btn, recordings_clear_btn, 
                recordings_list, recordings_open_btn, recordings_delete_btn,
                recordings_preview, recordings_download_btn, 
                recordings_info_text, recordings_download
            ),
            "config": (
                theme_selector, ui_refresh_btn, dark_mode, font_size, 
                border_radius, control_width, content_width, 
                custom_css, apply_css_btn, reset_ui_btn, 
                save_ui_btn, ui_status_text
            )
        }
        
        # 注册所有事件处理器
        register_all_events(demo, components)
        
        # 页脚
        with gr.Row(elem_classes=[CSS_CLASSES["FOOTER"]]):
            gr.Markdown("© 2025 Web Agent - 由人工智能提供支持")
    
    # 返回创建的界面    
    return demo
