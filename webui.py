import logging
import threading
from datetime import datetime, timedelta

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from src.ui.scheduler_tab import create_scheduler_tab
from src.utils.deep_research import deep_research
from src.utils.ding_talk import DingTalkRobot
from src.utils.scheduler_utils import SchedulerManager

load_dotenv()
import glob
import asyncio
import argparse
import os

logger = logging.getLogger(__name__)

import gradio as gr

from browser_use.agent.service import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import (
    BrowserContextWindowSize,
)
from src.utils.agent_state import AgentState, app_state

from src.agent.custom_agent import CustomAgent
from src.browser.custom_browser import CustomBrowser
from src.agent.custom_prompts import CustomSystemPrompt, CustomAgentMessagePrompt
from src.browser.custom_context import BrowserContextConfig
from src.controller.custom_controller import CustomController
from gradio.themes import Citrus, Default, Glass, Monochrome, Ocean, Origin, Soft, Base
from src.utils.utils import update_model_dropdown, get_latest_files, capture_screenshot, MissingAPIKeyError
from src.utils import utils

# Global variables for persistence
_global_browser = None
_global_browser_context = None
_global_agent = None

# Create the global agent state instance
_global_agent_state = AgentState()

# webui config
webui_config_manager = utils.ConfigManager()


def scan_and_register_components(blocks):
    """扫描一个 Blocks 对象并注册其中的所有交互式组件，但不包括按钮"""
    global webui_config_manager

    def traverse_blocks(block, prefix=""):
        registered = 0

        # 处理 Blocks 自身的组件
        if hasattr(block, "children"):
            for i, child in enumerate(block.children):
                if isinstance(child, gr.components.Component):
                    # 排除按钮 (Button) 组件
                    if getattr(child, "interactive", False) and not isinstance(child, gr.Button):
                        name = f"{prefix}component_{i}"
                        if hasattr(child, "label") and child.label:
                            # 使用标签作为名称的一部分
                            label = child.label
                            name = f"{prefix}{label}"
                        logger.debug(f"Registering component: {name}")
                        webui_config_manager.register_component(name, child)
                        registered += 1
                elif hasattr(child, "children"):
                    # 递归处理嵌套的 Blocks
                    new_prefix = f"{prefix}block_{i}_"
                    registered += traverse_blocks(child, new_prefix)

        return registered

    total = traverse_blocks(blocks)
    logger.info(f"Total registered components: {total}")


def save_current_config():
    return webui_config_manager.save_current_config()


def update_ui_from_config(config_file):
    return webui_config_manager.update_ui_from_config(config_file)


def resolve_sensitive_env_variables(text):
    """
    Replace environment variable placeholders ($SENSITIVE_*) with their values.
    Only replaces variables that start with SENSITIVE_.
    """
    if not text:
        return text

    import re

    # Find all $SENSITIVE_* patterns
    env_vars = re.findall(r'\$SENSITIVE_[A-Za-z0-9_]*', text)

    result = text
    for var in env_vars:
        # Remove the $ prefix to get the actual environment variable name
        env_name = var[1:]  # removes the $
        env_value = os.getenv(env_name)
        if env_value is not None:
            # Replace $SENSITIVE_VAR_NAME with its value
            result = result.replace(var, env_value)

    return result


# 调度器关闭钩子函数
def shutdown_scheduler():
    """
    在程序退出时关闭调度器
    """
    scheduler = app_state.get_scheduler()
    if scheduler and scheduler.running:
        logger.info("程序退出，关闭调度器")
        scheduler.shutdown(wait=False)


# 注册退出钩子
import atexit

atexit.register(shutdown_scheduler)


def start_scheduler(llm_provider,
                    llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key, research_task,
                    interval_minutes=60, title_prefix="深度研究", search_iterations=2, query_per_iter=3):
    """
    启动定时推送调度器

    参数:
        research_task: 研究任务内容
        interval_minutes: 执行间隔分钟数
        title_prefix: 标题前缀
        search_iterations: 最大搜索迭代次数
        query_per_iter: 每次迭代的最大查询数量

    返回:
        启动结果消息
    """
    try:
        logger.info(f"尝试启动调度器，任务: {research_task}, 间隔: {interval_minutes} 分钟")

        # 参数验证
        if not research_task or not isinstance(research_task, str) or research_task.strip() == "":
            error_msg = "研究任务必须为非空字符串"
            logger.error(error_msg)
            return error_msg

        if not isinstance(interval_minutes, (int, float)) or interval_minutes < 1:
            error_msg = "时间间隔必须是正整数分钟数"
            logger.error(error_msg)
            return error_msg

        # 确保间隔是整数分钟
        interval_minutes = int(interval_minutes)

        # 创建新调度器
        new_scheduler = BackgroundScheduler(
            executors={'default': ThreadPoolExecutor(max_workers=20)},
            job_defaults={
                'coalesce': True,  # 合并多个错过的任务
                'max_instances': 1,  # 同一个任务最大并行数
                'misfire_grace_time': 600  # 错过执行的宽限时间
            }
        )

        # 停止现有调度器(如果存在)
        current_scheduler = app_state.get_scheduler()
        if current_scheduler:
            try:
                logger.info("关闭现有调度器")
                current_scheduler.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"关闭旧调度器时发生异常: {str(e)}")

        # 立即更新全局调度器实例（使用异步方式，避免锁冲突）
        logger.info("异步设置新调度器为全局实例")
        app_state.set_scheduler_async(new_scheduler)

        # 设置定时触发器 - 使用分钟为单位
        # 将分钟转换为浮点数以支持精确计时
        trigger = IntervalTrigger(minutes=float(interval_minutes))

        # 准备定时任务参数
        job_args = {
            'research_task': research_task,
            'title_prefix': title_prefix,
            'search_iterations': search_iterations,
            'query_per_iter': query_per_iter
        }

        # 创建异步任务的包装函数
        def _scheduled_job_wrapper(**job_kwargs):
            """异步函数包装器函数，用于调度器调用"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 运行异步任务
                return loop.run_until_complete(
                    scheduled_job(**job_kwargs)
                )
            finally:
                loop.close()

        # 添加任务到调度器
        new_scheduler.add_job(
            _scheduled_job_wrapper,  # 使用包装函数
            trigger=trigger,
            kwargs=job_args,
            id='deep_research_job',
            replace_existing=True,
            misfire_grace_time=600
        )

        try:
            # 启动调度器 - 简化版本，不更新状态
            logger.info("开始启动调度器...")
            new_scheduler.start()
            logger.info(f"调度器已成功启动，下次执行将在 {interval_minutes} 分钟后")

            # 计算下次执行时间（仅用于生成消息）
            next_run_time = datetime.now() + timedelta(minutes=interval_minutes)

            # 启动后立即执行一次任务
            logger.info("调度器启动后立即执行一次任务...")

            # 创建一个新线程来执行任务，避免阻塞主线程
            def immediate_execute():
                try:
                    # 设置新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # 使用相同的参数运行任务
                        result = loop.run_until_complete(scheduled_job(
                            llm_provider=llm_provider,
                            llm_model_name=llm_model_name,
                            ollama_num_ctx=ollama_num_ctx,
                            llm_temperature=llm_temperature,
                            llm_base_url=llm_base_url,
                            llm_api_key=llm_api_key,
                            research_task=research_task,
                            title_prefix=title_prefix,
                            search_iterations=search_iterations,
                            query_per_iter=query_per_iter,
                            is_manual=True  # 标记为手动触发
                        ))
                        logger.info(f"立即执行任务结果: {result}")
                    finally:
                        loop.close()
                except Exception as e:
                    logger.error(f"立即执行任务异常: {str(e)}", exc_info=True)

            # 启动立即执行线程
            immediate_thread = threading.Thread(target=immediate_execute)
            immediate_thread.daemon = True  # 设置为守护线程，不阻塞主程序退出
            immediate_thread.start()

            # 生成成功消息
            if interval_minutes >= 60:
                hours = interval_minutes / 60
                if hours == int(hours):
                    # 整数小时
                    success_msg = f"调度器已成功启动，将每 {int(hours)} 小时执行一次。下次执行时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}"
                else:
                    # 小数小时
                    success_msg = f"调度器已成功启动，将每 {hours:.1f} 小时执行一次。下次执行时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                # 少于一小时，直接显示分钟
                success_msg = f"调度器已成功启动，将每 {interval_minutes} 分钟执行一次。下次执行时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}"

            logger.info(f"调度器启动成功: {success_msg}")
            return success_msg

        except Exception as e:
            error_msg = f"启动调度器时发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    except Exception as e:
        error_msg = f"启动调度器失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# 立即执行一次推送任务
async def run_push_task_once(llm_provider,
                             llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key,
                             research_task, title_prefix="深度研究", search_iterations=2, query_per_iter=3):
    """
    立即执行一次推送任务 (异步版本)

    参数:
        research_task: 研究任务内容
        title_prefix: 标题前缀
        search_iterations: 最大搜索迭代次数
        query_per_iter: 每次迭代的最大查询数量

    返回:
        执行结果消息, 状态文本, 下次执行时间文本
    """
    try:
        logger.info(f"用户触发立即执行一次按钮, 研究任务: {research_task}")

        # 调用异步的scheduled_job函数，指定为手动执行模式
        result, status_text, next_run_text = await scheduled_job(
            llm_provider,
            llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key,
            research_task,
            title_prefix,
            search_iterations,
            query_per_iter,
            is_manual=True
        )

        # 返回结果
        return f"执行成功: {result}", status_text, next_run_text

    except Exception as e:
        error_msg = f"执行失败: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # 更新错误状态
        app_state.update_scheduler_status(
            {"last_status": f"执行异常: {str(e)[:50]}", "last_run_time": datetime.now()},
            blocking=False
        )

        # 返回错误状态
        return error_msg, f"执行状态: 错误 ({str(e)[:50]})", "执行失败"


async def execute_push_task(llm_provider,
                            llm_model_name, llm_num_ctx, llm_temperature, llm_base_url, llm_api_key, research_task,
                            title_prefix="深度研究", search_iterations=2, query_per_iter=3):
    """
    执行深度研究并将结果推送到钉钉

    参数:
        research_task: 研究任务内容
        title_prefix: 标题前缀
        search_iterations: 最大搜索迭代次数
        query_per_iter: 每次迭代的最大查询数量

    返回:
        str: 结果消息
    """
    try:
        start_time = datetime.now()
        logger.info(f"深度研究任务开始执行: {research_task}")

        agent_state = AgentState()
        app_state.clear_stop()

        # 获取LLM模型 - 使用阿里云配置
        llm = utils.get_llm_model(
            provider=llm_provider,
            model_name=llm_model_name,
            num_ctx=llm_num_ctx,
            temperature=llm_temperature,
            base_url=llm_base_url,
            api_key=llm_api_key,
        )

        # 执行深度研究
        logger.info(f"开始执行深度研究: {research_task}")
        markdown_content, file_path = await deep_research(
            research_task,
            llm,
            agent_state,
            max_search_iterations=search_iterations,
            max_query_num=query_per_iter,
            use_vision=True,
            headless=True,
            use_own_browser=False
        )

        # 计算执行时间
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        duration_str = f"{duration:.2f}秒" if duration < 60 else f"{duration / 60:.2f}分钟"

        # 准备推送内容
        if markdown_content:
            # 标题包含任务简述和执行时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            title = f"{title_prefix}: {research_task[:20]}..." if len(
                research_task) > 20 else f"{title_prefix}: {research_task}"

            # 消息头部添加执行信息
            message_header = f"## {title}\n\n"
            message_header += f"**执行时间**: {current_time}\n\n"
            message_header += f"**耗时**: {duration_str}\n\n"
            message_header += f"**任务**: {research_task}\n\n"
            message_header += "---\n\n"

            # 拼接内容，钉钉限制消息长度，超长时需要截断
            message = message_header + markdown_content
            if len(message) > 20000:  # 钉钉消息长度限制
                message = message[:19700] + "\n\n...(内容已截断，完整内容请查看生成的文件)"

            # 发送到钉钉
            logger.info(f"发送研究结果到钉钉，标题: {title}, 内容长度: {len(message)}")
            try:
                send_result = DingTalkRobot.send_markdown(title, message)
                if send_result:
                    result_msg = f"任务执行成功并推送至钉钉，耗时: {duration_str}"
                    logger.info(result_msg)
                    app_state.update_scheduler_status({"last_status": "执行成功"}, blocking=False)
                else:
                    result_msg = f"任务执行成功但钉钉推送失败，耗时: {duration_str}"
                    logger.error(result_msg)
                    app_state.update_scheduler_status({"last_status": "推送失败"}, blocking=False)
            except Exception as e:
                result_msg = f"钉钉推送失败: {str(e)}"
                logger.error(result_msg, exc_info=True)
                app_state.update_scheduler_status({"last_status": "推送异常"}, blocking=False)
        else:
            result_msg = "任务执行失败，未获得研究结果"
            logger.warning(result_msg)
            app_state.update_scheduler_status({"last_status": "执行失败"}, blocking=False)

        return result_msg, markdown_content, file_path

    except Exception as e:
        error_msg = f"定时任务执行异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        app_state.update_scheduler_status({"last_status": f"执行异常: {str(e)[:50]}"})

        # 发送错误通知到钉钉
        try:
            error_title = "深度研究任务执行异常"
            error_content = f"## 深度研究任务执行异常\n\n"
            error_content += f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            error_content += f"**任务**: {research_task}\n\n"
            error_content += f"**错误**: {str(e)}\n\n"
            DingTalkRobot.send_markdown(error_title, error_content)
        except Exception as send_error:
            logger.error(f"发送错误通知失败: {str(send_error)}")

        return error_msg, None, None


async def scheduled_job(llm_provider,
                        llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key, research_task,
                        title_prefix="深度搜索", search_iterations=2, query_per_iter=3, is_manual=False):
    """
    定时任务入口函数 - 异步版本

    参数:
        research_task: 研究任务
        title_prefix: 标题前缀
        search_iterations: 搜索迭代次数
        query_per_iter: 每次迭代查询数量
        is_manual: 是否为手动触发的任务

    返回:
        执行结果、状态文本、下次执行时间文本
    """
    try:
        if not research_task or not isinstance(research_task, str) or research_task.strip() == "":
            raise ValueError("研究任务不能为空")

        mode = "手动" if is_manual else "定时"
        logger.info(f"{mode}任务触发，研究任务: {research_task}")

        # 获取代理状态
        app_state.get_agent_state()
        # 使用app_state替代agent_state调用clear_stop方法
        app_state.clear_stop()

        # 获取超时设置
        timeout_seconds = int(os.getenv("TASK_TIMEOUT", "600"))

        # 直接异步执行任务
        try:
            # 使用asyncio.wait_for设置超时
            result, markdown_content, file_path = await asyncio.wait_for(
                execute_push_task(
                    llm_provider,
                    llm_model_name,
                    ollama_num_ctx,
                    llm_temperature,
                    llm_base_url,
                    llm_api_key,
                    research_task,
                    title_prefix,
                    search_iterations,
                    query_per_iter
                ),
                timeout=timeout_seconds
            )

            # 任务成功完成
            logger.info(f"{mode}任务执行完成: {research_task}")

            # 更新最终状态（不使用中间状态）
            app_state.update_scheduler_status(
                {"last_status": f"{mode}执行完成", "last_run_time": datetime.now()},
                blocking=False
            )

            # 返回成功结果
            status_text = f"执行状态: 成功完成"
            next_run_text = "手动执行完成"
            if not is_manual:
                next_run = get_next_run_time()
                if next_run:
                    next_run_text = f"下次执行时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}"

            return result, status_text, next_run_text

        except asyncio.TimeoutError:
            # 处理任务超时
            error_msg = f"任务执行超时（{timeout_seconds}秒）"
            logger.error(error_msg)

            # 更新超时状态
            app_state.update_scheduler_status(
                {"last_status": "执行超时", "last_run_time": datetime.now()},
                blocking=False
            )

            # 尝试发送超时通知
            try:
                timeout_title = f"【{title_prefix}】任务执行超时"
                timeout_text = f"研究任务 '{research_task}' 执行超时（{timeout_seconds}秒）"
                # 如果需要发送通知，可以在这里添加代码
            except Exception as e:
                logger.error(f"发送超时通知失败：{str(e)}")

            return f"执行超时（{timeout_seconds}秒）", "执行状态: 超时", "执行失败"

    except Exception as e:
        # 处理其他异常
        error_msg = f"定时任务执行异常: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # 更新异常状态
        app_state.update_scheduler_status(
            {"last_status": f"执行异常: {str(e)[:50]}", "last_run_time": datetime.now()},
            blocking=False
        )

        return f"任务异常: {str(e)}", f"执行状态: 异常 ({str(e)[:50]})", "执行失败"


async def stop_agent():
    """Request the agent to stop and update UI with enhanced feedback"""
    global _global_agent

    try:
        if _global_agent is not None:
            # Request stop
            _global_agent.stop()
        # Update UI immediately
        message = "Stop requested - the agent will halt at the next safe point"
        logger.info(f"🛑 {message}")

        # Return UI updates
        return (
            gr.update(value="Stopping...", interactive=False),  # stop_button
            gr.update(interactive=False),  # run_button
        )
    except Exception as e:
        error_msg = f"Error during stop: {str(e)}"
        logger.error(error_msg)
        return (
            gr.update(value="Stop", interactive=True),
            gr.update(interactive=True)
        )


async def stop_research_agent():
    """Request the agent to stop and update UI with enhanced feedback"""
    global _global_agent_state

    try:
        # Request stop
        _global_agent_state.request_stop()

        # Update UI immediately
        message = "Stop requested - the agent will halt at the next safe point"
        logger.info(f"🛑 {message}")

        # Return UI updates
        return (  # errors_output
            gr.update(value="Stopping...", interactive=False),  # stop_button
            gr.update(interactive=False),  # run_button
        )
    except Exception as e:
        error_msg = f"Error during stop: {str(e)}"
        logger.error(error_msg)
        return (
            gr.update(value="Stop", interactive=True),
            gr.update(interactive=True)
        )


async def run_browser_agent(
        agent_type,
        llm_provider,
        llm_model_name,
        llm_num_ctx,
        llm_temperature,
        llm_base_url,
        llm_api_key,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        enable_recording,
        task,
        add_infos,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_calling_method,
        chrome_cdp,
        max_input_tokens
):
    try:
        # Disable recording if the checkbox is unchecked
        if not enable_recording:
            save_recording_path = None

        # Ensure the recording directory exists if recording is enabled
        if save_recording_path:
            os.makedirs(save_recording_path, exist_ok=True)

        # Get the list of existing videos before the agent runs
        existing_videos = set()
        if save_recording_path:
            existing_videos = set(
                glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4"))
                + glob.glob(os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))
            )

        task = resolve_sensitive_env_variables(task)

        # Run the agent
        llm = utils.get_llm_model(
            provider=llm_provider,
            model_name=llm_model_name,
            num_ctx=llm_num_ctx,
            temperature=llm_temperature,
            base_url=llm_base_url,
            api_key=llm_api_key,
        )
        if agent_type == "org":
            final_result, errors, model_actions, model_thoughts, trace_file, history_file = await run_org_agent(
                llm=llm,
                use_own_browser=use_own_browser,
                keep_browser_open=keep_browser_open,
                headless=headless,
                disable_security=disable_security,
                window_w=window_w,
                window_h=window_h,
                save_recording_path=save_recording_path,
                save_agent_history_path=save_agent_history_path,
                save_trace_path=save_trace_path,
                task=task,
                max_steps=max_steps,
                use_vision=use_vision,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method,
                chrome_cdp=chrome_cdp,
                max_input_tokens=max_input_tokens
            )
        elif agent_type == "custom":
            final_result, errors, model_actions, model_thoughts, trace_file, history_file = await run_custom_agent(
                llm=llm,
                use_own_browser=use_own_browser,
                keep_browser_open=keep_browser_open,
                headless=headless,
                disable_security=disable_security,
                window_w=window_w,
                window_h=window_h,
                save_recording_path=save_recording_path,
                save_agent_history_path=save_agent_history_path,
                save_trace_path=save_trace_path,
                task=task,
                add_infos=add_infos,
                max_steps=max_steps,
                use_vision=use_vision,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method,
                chrome_cdp=chrome_cdp,
                max_input_tokens=max_input_tokens
            )
        else:
            raise ValueError(f"Invalid agent type: {agent_type}")

        # Get the list of videos after the agent runs (if recording is enabled)
        # latest_video = None
        # if save_recording_path:
        #     new_videos = set(
        #         glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4"))
        #         + glob.glob(os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))
        #     )
        #     if new_videos - existing_videos:
        #         latest_video = list(new_videos - existing_videos)[0]  # Get the first new video

        gif_path = os.path.join(os.path.dirname(__file__), "agent_history.gif")

        return (
            final_result,
            errors,
            model_actions,
            model_thoughts,
            gif_path,
            trace_file,
            history_file,
            gr.update(value="Stop", interactive=True),  # Re-enable stop button
            gr.update(interactive=True)  # Re-enable run button
        )

    except MissingAPIKeyError as e:
        logger.error(str(e))
        raise gr.Error(str(e), print_exception=False)

    except Exception as e:
        import traceback
        traceback.print_exc()
        errors = str(e) + "\n" + traceback.format_exc()
        return (
            '',  # final_result
            errors,  # errors
            '',  # model_actions
            '',  # model_thoughts
            None,  # latest_video
            None,  # history_file
            None,  # trace_file
            gr.update(value="Stop", interactive=True),  # Re-enable stop button
            gr.update(interactive=True)  # Re-enable run button
        )


async def run_org_agent(
        llm,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        task,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_calling_method,
        chrome_cdp,
        max_input_tokens
):
    try:
        global _global_browser, _global_browser_context, _global_agent

        extra_chromium_args = ["--accept_downloads=True", f"--window-size={window_w},{window_h}"]
        cdp_url = chrome_cdp

        if use_own_browser:
            cdp_url = os.getenv("CHROME_CDP", chrome_cdp)
            chrome_path = os.getenv("CHROME_PATH", None)
            if chrome_path == "":
                chrome_path = None
            chrome_user_data = os.getenv("CHROME_USER_DATA", None)
            if chrome_user_data:
                extra_chromium_args += [f"--user-data-dir={chrome_user_data}"]
        else:
            chrome_path = None

        if _global_browser is None:
            _global_browser = Browser(
                config=BrowserConfig(
                    headless=headless,
                    cdp_url=cdp_url,
                    disable_security=disable_security,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=extra_chromium_args,
                )
            )

        if _global_browser_context is None:
            _global_browser_context = await _global_browser.new_context(
                config=BrowserContextConfig(
                    trace_path=save_trace_path if save_trace_path else None,
                    save_recording_path=save_recording_path if save_recording_path else None,
                    save_downloads_path="./tmp/downloads",
                    no_viewport=False,
                    browser_window_size=BrowserContextWindowSize(
                        width=window_w, height=window_h
                    ),
                )
            )

        if _global_agent is None:
            _global_agent = Agent(
                task=task,
                llm=llm,
                use_vision=use_vision,
                browser=_global_browser,
                browser_context=_global_browser_context,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method,
                max_input_tokens=max_input_tokens,
                generate_gif=True
            )
        history = await _global_agent.run(max_steps=max_steps)

        history_file = os.path.join(save_agent_history_path, f"{_global_agent.state.agent_id}.json")
        _global_agent.save_history(history_file)

        final_result = history.final_result()
        errors = history.errors()
        model_actions = history.model_actions()
        model_thoughts = history.model_thoughts()

        trace_file = get_latest_files(save_trace_path)

        return final_result, errors, model_actions, model_thoughts, trace_file.get('.zip'), history_file
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors = str(e) + "\n" + traceback.format_exc()
        return '', errors, '', '', None, None
    finally:
        _global_agent = None
        # Handle cleanup based on persistence configuration
        if not keep_browser_open:
            if _global_browser_context:
                await _global_browser_context.close()
                _global_browser_context = None

            if _global_browser:
                await _global_browser.close()
                _global_browser = None


async def run_custom_agent(
        llm,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        task,
        add_infos,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_calling_method,
        chrome_cdp,
        max_input_tokens
):
    try:
        global _global_browser, _global_browser_context, _global_agent

        extra_chromium_args = ["--accept_downloads=True", f"--window-size={window_w},{window_h}"]
        cdp_url = chrome_cdp
        if use_own_browser:
            cdp_url = os.getenv("CHROME_CDP", chrome_cdp)

            chrome_path = os.getenv("CHROME_PATH", None)
            if chrome_path == "":
                chrome_path = None
            chrome_user_data = os.getenv("CHROME_USER_DATA", None)
            if chrome_user_data:
                extra_chromium_args += [f"--user-data-dir={chrome_user_data}"]
        else:
            chrome_path = None

        controller = CustomController()

        # Initialize global browser if needed
        # if chrome_cdp not empty string nor None
        if (_global_browser is None) or (cdp_url and cdp_url != "" and cdp_url != None):
            _global_browser = CustomBrowser(
                config=BrowserConfig(
                    headless=headless,
                    disable_security=disable_security,
                    cdp_url=cdp_url,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=extra_chromium_args,
                )
            )

        if _global_browser_context is None or (chrome_cdp and cdp_url != "" and cdp_url != None):
            _global_browser_context = await _global_browser.new_context(
                config=BrowserContextConfig(
                    trace_path=save_trace_path if save_trace_path else None,
                    save_recording_path=save_recording_path if save_recording_path else None,
                    no_viewport=False,
                    save_downloads_path="./tmp/downloads",
                    browser_window_size=BrowserContextWindowSize(
                        width=window_w, height=window_h
                    ),
                )
            )

        # Create and run agent
        if _global_agent is None:
            _global_agent = CustomAgent(
                task=task,
                add_infos=add_infos,
                use_vision=use_vision,
                llm=llm,
                browser=_global_browser,
                browser_context=_global_browser_context,
                controller=controller,
                system_prompt_class=CustomSystemPrompt,
                agent_prompt_class=CustomAgentMessagePrompt,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method,
                max_input_tokens=max_input_tokens,
                generate_gif=True
            )
        history = await _global_agent.run(max_steps=max_steps)

        history_file = os.path.join(save_agent_history_path, f"{_global_agent.state.agent_id}.json")
        _global_agent.save_history(history_file)

        final_result = history.final_result()
        errors = history.errors()
        model_actions = history.model_actions()
        model_thoughts = history.model_thoughts()

        trace_file = get_latest_files(save_trace_path)

        return final_result, errors, model_actions, model_thoughts, trace_file.get('.zip'), history_file
    except Exception as e:
        import traceback
        traceback.print_exc()
        errors = str(e) + "\n" + traceback.format_exc()
        return '', errors, '', '', None, None
    finally:
        _global_agent = None
        # Handle cleanup based on persistence configuration
        if not keep_browser_open:
            if _global_browser_context:
                await _global_browser_context.close()
                _global_browser_context = None

            if _global_browser:
                await _global_browser.close()
                _global_browser = None


async def run_with_stream(
        agent_type,
        llm_provider,
        llm_model_name,
        llm_num_ctx,
        llm_temperature,
        llm_base_url,
        llm_api_key,
        use_own_browser,
        keep_browser_open,
        headless,
        disable_security,
        window_w,
        window_h,
        save_recording_path,
        save_agent_history_path,
        save_trace_path,
        enable_recording,
        task,
        add_infos,
        max_steps,
        use_vision,
        max_actions_per_step,
        tool_calling_method,
        chrome_cdp,
        max_input_tokens
):
    global _global_agent

    stream_vw = 80
    stream_vh = int(80 * window_h // window_w)
    if not headless:
        result = await run_browser_agent(
            agent_type=agent_type,
            llm_provider=llm_provider,
            llm_model_name=llm_model_name,
            llm_num_ctx=llm_num_ctx,
            llm_temperature=llm_temperature,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            use_own_browser=use_own_browser,
            keep_browser_open=keep_browser_open,
            headless=headless,
            disable_security=disable_security,
            window_w=window_w,
            window_h=window_h,
            save_recording_path=save_recording_path,
            save_agent_history_path=save_agent_history_path,
            save_trace_path=save_trace_path,
            enable_recording=enable_recording,
            task=task,
            add_infos=add_infos,
            max_steps=max_steps,
            use_vision=use_vision,
            max_actions_per_step=max_actions_per_step,
            tool_calling_method=tool_calling_method,
            chrome_cdp=chrome_cdp,
            max_input_tokens=max_input_tokens
        )
        # Add HTML content at the start of the result array
        yield [gr.update(visible=False)] + list(result)
    else:
        try:
            # Run the browser agent in the background
            agent_task = asyncio.create_task(
                run_browser_agent(
                    agent_type=agent_type,
                    llm_provider=llm_provider,
                    llm_model_name=llm_model_name,
                    llm_num_ctx=llm_num_ctx,
                    llm_temperature=llm_temperature,
                    llm_base_url=llm_base_url,
                    llm_api_key=llm_api_key,
                    use_own_browser=use_own_browser,
                    keep_browser_open=keep_browser_open,
                    headless=headless,
                    disable_security=disable_security,
                    window_w=window_w,
                    window_h=window_h,
                    save_recording_path=save_recording_path,
                    save_agent_history_path=save_agent_history_path,
                    save_trace_path=save_trace_path,
                    enable_recording=enable_recording,
                    task=task,
                    add_infos=add_infos,
                    max_steps=max_steps,
                    use_vision=use_vision,
                    max_actions_per_step=max_actions_per_step,
                    tool_calling_method=tool_calling_method,
                    chrome_cdp=chrome_cdp,
                    max_input_tokens=max_input_tokens
                )
            )

            # Initialize values for streaming
            html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Using browser...</h1>"
            final_result = errors = model_actions = model_thoughts = ""
            recording_gif = trace = history_file = None

            # Periodically update the stream while the agent task is running
            while not agent_task.done():
                try:
                    encoded_screenshot = await capture_screenshot(_global_browser_context)
                    if encoded_screenshot is not None:
                        html_content = f'<img src="data:image/jpeg;base64,{encoded_screenshot}" style="width:{stream_vw}vw; height:{stream_vh}vh ; border:1px solid #ccc;">'
                    else:
                        html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Waiting for browser session...</h1>"
                except Exception as e:
                    html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Waiting for browser session...</h1>"

                if _global_agent and _global_agent.state.stopped:
                    yield [
                        gr.HTML(value=html_content, visible=True),
                        final_result,
                        errors,
                        model_actions,
                        model_thoughts,
                        recording_gif,
                        trace,
                        history_file,
                        gr.update(value="Stopping...", interactive=False),  # stop_button
                        gr.update(interactive=False),  # run_button
                    ]
                    break
                else:
                    yield [
                        gr.HTML(value=html_content, visible=True),
                        final_result,
                        errors,
                        model_actions,
                        model_thoughts,
                        recording_gif,
                        trace,
                        history_file,
                        gr.update(),  # Re-enable stop button
                        gr.update()  # Re-enable run button
                    ]
                await asyncio.sleep(0.1)

            # Once the agent task completes, get the results
            try:
                result = await agent_task
                final_result, errors, model_actions, model_thoughts, recording_gif, trace, history_file, stop_button, run_button = result
            except gr.Error:
                final_result = ""
                model_actions = ""
                model_thoughts = ""
                recording_gif = trace = history_file = None

            except Exception as e:
                errors = f"Agent error: {str(e)}"

            yield [
                gr.HTML(value=html_content, visible=True),
                final_result,
                errors,
                model_actions,
                model_thoughts,
                recording_gif,
                trace,
                history_file,
                stop_button,
                run_button
            ]

        except Exception as e:
            import traceback
            yield [
                gr.HTML(
                    value=f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>Waiting for browser session...</h1>",
                    visible=True),
                "",
                f"Error: {str(e)}\n{traceback.format_exc()}",
                "",
                "",
                None,
                None,
                None,
                gr.update(value="Stop", interactive=True),  # Re-enable stop button
                gr.update(interactive=True)  # Re-enable run button
            ]


# Define the theme map globally
theme_map = {
    "Default": Default(),
    "Soft": Soft(),
    "Monochrome": Monochrome(),
    "Glass": Glass(),
    "Origin": Origin(),
    "Citrus": Citrus(),
    "Ocean": Ocean(),
    "Base": Base()
}


async def close_global_browser():
    global _global_browser, _global_browser_context

    if _global_browser_context:
        await _global_browser_context.close()
        _global_browser_context = None

    if _global_browser:
        await _global_browser.close()
        _global_browser = None


# Function to optimize the research task prompt
async def optimize_prompt(prompt_text, llm_provider,
                          llm_model_name, llm_num_ctx, llm_temperature, llm_base_url, llm_api_key):
    try:
        llm = utils.get_llm_model(
            provider=llm_provider,
            model_name=llm_model_name,
            num_ctx=llm_num_ctx,
            temperature=llm_temperature,
            base_url=llm_base_url,
            api_key=llm_api_key,
        )
        prompt = '''你是一个研究任务扩展专家。当用户提出简短的研究需求时，请你从用户的角度出发，将其扩展为更全面、更有深度的研究请求。具体来说：
        1.识别用户研究主题的核心领域
        2.补充3 - 5个可能的研究角度或维度
        3.提出2 - 3个可能的分析方法或步骤
        4.明确1 - 2个期望的研究成果或应用

        保持用户的第一人称语气，直接返回扩展后的研究需求，不要添加任何解释。例如，当用户输入'我要一份牛奶分析报告'时，你应该将其扩展为'我需要一份全面的牛奶分析报告，希望从市场趋势、营养成分对比、消费者偏好和价格波动等角度进行深入研究。建议采用数据可视化方式呈现市场份额变化，并通过对比分析揭示不同品牌的优劣势。最终希望该报告能指导我的购买决策并提供未来牛奶行业发展趋势的洞察。'

        用户输入的是：'''
        ai_query_msg = llm.invoke(prompt + prompt_text)
        return ai_query_msg.content
    except Exception as e:
        logger.error(f"Error optimizing prompt: {str(e)}")
        return f"优化失败: {str(e)}"


async def run_deep_search(
        enable_schedule,
        schedule_interval,
        schedule_title,
        research_task, max_search_iteration_input, max_query_per_iter_input, llm_provider,
        llm_model_name, llm_num_ctx, llm_temperature, llm_base_url, llm_api_key, use_vision,
        use_own_browser, headless, chrome_cdp):
    from src.utils.deep_research import deep_research
    from src.utils.ppt_download import get_ppt
    import os
    global _global_agent_state

    # Clear any previous stop request
    # 使用app_state替代agent_state调用clear_stop方法
    app_state.clear_stop()

    llm = utils.get_llm_model(
        provider=llm_provider,
        model_name=llm_model_name,
        num_ctx=llm_num_ctx,
        temperature=llm_temperature,
        base_url=llm_base_url,
        api_key=llm_api_key,
    )

    if enable_schedule:
        scheduler = SchedulerManager()
        # 使用关键字参数传递，避免位置参数问题

        # 定义一个全局存储结果的字典
        result_store = {}

        # 定义回调函数来处理返回值
        async def process_result(markdown_content, file_path):
            # 存储结果
            result_store['markdown_content'] = markdown_content
            result_store['file_path'] = file_path

            # 生成PPT
            if file_path and os.path.exists(file_path) and markdown_content:
                try:
                    # 调用get_ppt函数生成PPT
                    ppt_path = get_ppt(markdown_content)
                    result_store['ppt_path'] = ppt_path

                    # 记录日志
                    logger.info(f"计划任务生成PPT成功: {ppt_path}")
                except Exception as e:
                    logger.error(f"计划任务生成PPT失败: {str(e)}")

        # 自定义包装异步函数，确保参数正确传递
        async def wrapped_deep_research():
            result = await deep_research(
                task=research_task,
                llm=llm,
                agent_state=_global_agent_state,
                max_search_iterations=max_search_iteration_input,
                max_query_num=max_query_per_iter_input,
                use_vision=use_vision,
                headless=headless,
                use_own_browser=use_own_browser,
                chrome_cdp=chrome_cdp
            )
            # 处理结果
            if isinstance(result, tuple) and len(result) >= 2:
                markdown_content, file_path = result[0], result[1]
                await process_result(markdown_content, file_path)
            return result

        # 添加包装后的异步任务
        async_job_id = scheduler.add_async_job(
            async_func=wrapped_deep_research,
            trigger='interval',
            minutes=schedule_interval,  # 使用传入的间隔参数，转换为分钟
            job_id=f"deep_research_{schedule_title}"  # 添加有意义的任务ID
        )

        # 立即执行一次任务
        scheduler.execute_job_now(async_job_id)

        # 轮询等待result_store有值，最多等待60秒
        wait_time = 0
        max_wait_time = 600  # 最大等待时间，秒
        check_interval = 2   # 检查间隔，秒

        logger.info(f"开始等待异步任务结果...")

        # 初始化结果变量
        markdown_content, file_path = None, None

        # 轮询等待结果
        while wait_time < max_wait_time:
            # 检查result_store是否有值
            if 'markdown_content' in result_store and 'file_path' in result_store:
                markdown_content = result_store.get('markdown_content')
                file_path = result_store.get('file_path')
                logger.info(f"成功获取异步任务结果，耗时: {wait_time}秒")
                break

            # 等待一段时间再检查
            await asyncio.sleep(check_interval)
            wait_time += check_interval
            logger.info(f"等待异步任务结果: {wait_time}秒...")

        # 如果超时仍未获取结果
        if wait_time >= max_wait_time:
            logger.warning(f"等待异步任务结果超时({max_wait_time}秒)，继续处理")

        # 返回结果，如果未获取到结果则为None
        logger.info(f"返回结果: 文件路径={file_path}, 内容长度={len(markdown_content) if markdown_content else 0}")
        if len(markdown_content) > 20000:  # 钉钉消息长度限制
            markdown_content = markdown_content[:19700] + "\n\n...(内容已截断，完整内容请查看生成的文件)"

        DingTalkRobot.send_markdown("Agent 推送报告", markdown_content)

        return markdown_content, file_path, result_store.get('ppt_path'), gr.update(value="Stop", interactive=True), gr.update(interactive=True)
    else:
        markdown_content, file_path = await deep_research(task=research_task,
                                                          llm=llm,
                                                          agent_state=_global_agent_state,
                                                          max_search_iterations=max_search_iteration_input,
                                                          max_query_num=max_query_per_iter_input,
                                                          use_vision=use_vision,
                                                          headless=headless,
                                                          use_own_browser=use_own_browser,
                                                          chrome_cdp=chrome_cdp
                                                          )

        # 生成PPT并返回文件路径
        ppt_path = None
        if file_path and os.path.exists(file_path) and markdown_content:
            try:
                # 调用get_ppt函数生成PPT
                ppt_path = get_ppt(markdown_content)
            except Exception as e:
                logger.error(f"生成PPT失败: {str(e)}")
        else:
            # 计划模式的结果将在异步回调函数中处理
            logger.info("计划任务已初始化，结果将在异步任务中处理")

        if len(markdown_content) > 20000:  # 钉钉消息长度限制
            markdown_content = markdown_content[:19700] + "\n\n...(内容已截断，完整内容请查看生成的文件)"

        DingTalkRobot.send_markdown("Agent 推送报告", markdown_content)

        return markdown_content, file_path, ppt_path, gr.update(value="Stop", interactive=True), gr.update(interactive=True)


def get_next_run_time():
    """
    获取下一次定时任务执行时间

    返回:
        datetime: 下一次执行的时间点，如果没有调度任务则返回None
    """
    try:
        # 获取当前调度器实例
        scheduler = app_state.get_scheduler()
        if not scheduler or not hasattr(scheduler, "running") or not scheduler.running:
            return None

        # 获取所有任务
        jobs = scheduler.get_jobs()
        if not jobs:
            return None

        # 找出下一个要执行的任务时间
        next_run_time = None
        for job in jobs:
            if job.next_run_time:
                if next_run_time is None or job.next_run_time < next_run_time:
                    next_run_time = job.next_run_time

        return next_run_time
    except Exception as e:
        logger.error(f"获取下一次执行时间异常: {str(e)}")
        return None


def stop_scheduler():
    """
    停止定时推送调度器

    返回:
        停止结果消息
    """
    try:
        logger.info("尝试停止调度器...")

        # 获取当前调度器实例
        scheduler = app_state.get_scheduler()

        # 判断调度器是否存在并且在运行
        if scheduler and hasattr(scheduler, "running") and scheduler.running:
            logger.info("正在关闭运行中的调度器...")

            # 尝试关闭调度器
            try:
                scheduler.shutdown(wait=False)
                logger.info("调度器已成功关闭")
            except Exception as shutdown_error:
                logger.warning(f"关闭调度器时发生异常: {str(shutdown_error)}", exc_info=True)

            # 释放调度器实例
            app_state.set_scheduler(None)

            # 更新调度器状态(非阻塞模式)
            scheduler_status = {
                "running": False,
                "next_run_time": None,
                "last_status": "调度器已停止",
                "last_update_time": datetime.now()
            }
            app_state.update_scheduler_status(scheduler_status, blocking=False)
            logger.info("已请求更新调度器状态为已停止")

            success_msg = "调度器已成功停止"
            logger.info(success_msg)
            return success_msg
        else:
            info_msg = "调度器已经处于停止状态"
            logger.info(info_msg)
            return info_msg

    except Exception as e:
        error_msg = f"停止调度器时发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # 尝试更新错误状态
        try:
            app_state.update_scheduler_status({
                "running": False,
                "last_status": f"停止失败: {str(e)[:50]}",
                "last_update_time": datetime.now(),
                "error": str(e)
            }, blocking=False)
            logger.info(f"已请求更新调度器停止失败状态")
        except Exception as status_error:
            logger.error(f"无法更新调度器状态: {str(status_error)}", exc_info=True)

        return error_msg


def create_ui(theme_name="Ocean"):
    css = """
    .gradio-container {
        width: 60vw !important; 
        max-width: 60% !important; 
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 20px !important;
    }
    .header-text {
        text-align: center;
        margin-bottom: 30px;
    }
    .theme-section {
        margin-bottom: 20px;
        padding: 15px;
        border-radius: 10px;
    }
    """

    with gr.Blocks(
            title="Browser Use WebUI", theme=theme_map[theme_name], css=css
    ) as demo:
        with gr.Row():
            gr.Markdown(
                """
                # 🌐 Browser Use WebUI
                ### Control your browser with AI assistance
                """,
                elem_classes=["header-text"],
            )

        with gr.Tabs() as tabs:
            with gr.TabItem("⚙️ Agent Settings", id=1):
                with gr.Group():
                    agent_type = gr.Radio(
                        ["org", "custom"],
                        label="Agent Type",
                        value="custom",
                        info="Select the type of agent to use",
                        interactive=True
                    )
                    with gr.Column():
                        max_steps = gr.Slider(
                            minimum=1,
                            maximum=200,
                            value=100,
                            step=1,
                            label="Max Run Steps",
                            info="Maximum number of steps the agent will take",
                            interactive=True
                        )
                        max_actions_per_step = gr.Slider(
                            minimum=1,
                            maximum=100,
                            value=10,
                            step=1,
                            label="Max Actions per Step",
                            info="Maximum number of actions the agent will take per step",
                            interactive=True
                        )
                    with gr.Column():
                        use_vision = gr.Checkbox(
                            label="Use Vision",
                            value=True,
                            info="Enable visual processing capabilities",
                            interactive=True
                        )
                        max_input_tokens = gr.Number(
                            label="Max Input Tokens",
                            value=5120000,
                            precision=0,
                            interactive=True
                        )
                        tool_calling_method = gr.Dropdown(
                            label="Tool Calling Method",
                            value="auto",
                            interactive=True,
                            allow_custom_value=True,  # Allow users to input custom model names
                            choices=["auto", "json_schema", "function_calling"],
                            info="Tool Calls Funtion Name",
                            visible=False
                        )

            with gr.TabItem("🔧 LLM Settings", id=2):
                with gr.Group():
                    llm_provider = gr.Dropdown(
                        choices=[provider for provider, model in utils.model_names.items()],
                        label="LLM Provider",
                        value="alibaba",
                        info="Select your preferred language model provider",
                        interactive=True
                    )
                    llm_model_name = gr.Dropdown(
                        label="Model Name",
                        choices=utils.model_names['alibaba'],
                        value="qwen-max",
                        interactive=True,
                        allow_custom_value=True,  # Allow users to input custom model names
                        info="Select a model in the dropdown options or directly type a custom model name"
                    )
                    ollama_num_ctx = gr.Slider(
                        minimum=2 ** 8,
                        maximum=2 ** 16,
                        value=16000,
                        step=1,
                        label="Ollama Context Length",
                        info="Controls max context length model needs to handle (less = faster)",
                        visible=False,
                        interactive=True
                    )
                    llm_temperature = gr.Slider(
                        minimum=0.0,
                        maximum=2.0,
                        value=0.2,
                        step=0.1,
                        label="Temperature",
                        info="Controls randomness in model outputs",
                        interactive=True
                    )
                    with gr.Row():
                        llm_base_url = gr.Textbox(
                            label="Base URL",
                            value="",
                            info="API endpoint URL (if required)"
                        )
                        llm_api_key = gr.Textbox(
                            label="API Key",
                            type="password",
                            value="",
                            info="Your API key (leave blank to use .env)"
                        )

            # Change event to update context length slider
            def update_llm_num_ctx_visibility(llm_provider):
                return gr.update(visible=llm_provider == "ollama")

            # Bind the change event of llm_provider to update the visibility of context length slider
            llm_provider.change(
                fn=update_llm_num_ctx_visibility,
                inputs=llm_provider,
                outputs=ollama_num_ctx
            )

            with gr.TabItem("🌐 Browser Settings", id=3):
                with gr.Group():
                    with gr.Row():
                        use_own_browser = gr.Checkbox(
                            label="Use Own Browser",
                            value=True,
                            info="Use your existing browser instance",
                            interactive=True
                        )
                        keep_browser_open = gr.Checkbox(
                            label="Keep Browser Open",
                            value=False,
                            info="Keep Browser Open between Tasks",
                            interactive=True
                        )
                        headless = gr.Checkbox(
                            label="Headless Mode",
                            value=False,
                            info="Run browser without GUI",
                            interactive=True
                        )
                        disable_security = gr.Checkbox(
                            label="Disable Security",
                            value=True,
                            info="Disable browser security features",
                            interactive=True
                        )
                        enable_recording = gr.Checkbox(
                            label="Enable Recording",
                            value=True,
                            info="Enable saving browser recordings",
                            interactive=True
                        )

                    with gr.Row():
                        window_w = gr.Number(
                            label="Window Width",
                            value=1280,
                            info="Browser window width",
                            interactive=True
                        )
                        window_h = gr.Number(
                            label="Window Height",
                            value=1100,
                            info="Browser window height",
                            interactive=True
                        )

                    chrome_cdp = gr.Textbox(
                        label="CDP URL",
                        placeholder="http://localhost:9222",
                        value="",
                        info="CDP for google remote debugging",
                        interactive=True,  # Allow editing only if recording is enabled
                    )

                    save_recording_path = gr.Textbox(
                        label="Recording Path",
                        placeholder="e.g. ./tmp/record_videos",
                        value="./tmp/record_videos",
                        info="Path to save browser recordings",
                        interactive=True,  # Allow editing only if recording is enabled
                    )

                    save_trace_path = gr.Textbox(
                        label="Trace Path",
                        placeholder="e.g. ./tmp/traces",
                        value="./tmp/traces",
                        info="Path to save Agent traces",
                        interactive=True,
                    )

                    save_agent_history_path = gr.Textbox(
                        label="Agent History Save Path",
                        placeholder="e.g., ./tmp/agent_history",
                        value="./tmp/agent_history",
                        info="Specify the directory where agent history should be saved.",
                        interactive=True,
                    )

            with gr.TabItem("🤖 Run Agent", id=4):
                task = gr.Textbox(
                    label="Task Description",
                    lines=4,
                    placeholder="Enter your task here...",
                    value="go to google.com and type 'OpenAI' click search and give me the first url",
                    info="Describe what you want the agent to do",
                    interactive=True
                )
                add_infos = gr.Textbox(
                    label="Additional Information",
                    lines=3,
                    placeholder="Add any helpful context or instructions...",
                    info="Optional hints to help the LLM complete the task",
                    value="",
                    interactive=True
                )

                with gr.Row():
                    run_button = gr.Button("▶️ Run Agent", variant="primary", scale=2)
                    stop_button = gr.Button("⏹️ Stop", variant="stop", scale=1)

                with gr.Row():
                    browser_view = gr.HTML(
                        value="<h1 style='width:80vw; height:50vh'>Waiting for browser session...</h1>",
                        label="Live Browser View",
                        visible=False
                    )

                gr.Markdown("### Results")
                with gr.Row():
                    with gr.Column():
                        final_result_output = gr.Textbox(
                            label="Final Result", lines=3, show_label=True
                        )
                    with gr.Column():
                        errors_output = gr.Textbox(
                            label="Errors", lines=3, show_label=True
                        )
                with gr.Row():
                    with gr.Column():
                        model_actions_output = gr.Textbox(
                            label="Model Actions", lines=3, show_label=True, visible=False
                        )
                    with gr.Column():
                        model_thoughts_output = gr.Textbox(
                            label="Model Thoughts", lines=3, show_label=True, visible=False
                        )
                recording_gif = gr.Image(label="Result GIF", format="gif")
                trace_file = gr.File(label="Trace File")
                agent_history_file = gr.File(label="Agent History")

            with gr.TabItem("🧐 Deep Research", id=5):
                research_task_input = gr.Textbox(label="Research Task", lines=5,
                                                 value="""访问抖音店铺后台：https://compass.jinritemai.com/shop查看相关数据 
然后访问店铺榜单、商品榜单、行业搜索词榜单、看后搜索词榜单，链接分别为：
https://compass.jinritemai.com/shop/chance/search-shop-rank?rank_type=2&from_page=%2Fshop%2Fchance%2Fsearch-word-rank&from=sy&btm_ppre=a6187.b01487.c0.d0&btm_pre=a6187.b17762.c0.d0&btm_show_id=a1969687-d888-471f-b4ea-070065bd18d9

https://compass.jinritemai.com/shop/chance/search-rank-product?rank_type=1&from_page=%2Fshop%2Fchance%2Fsearch-shop-rank&from=sy&btm_ppre=a6187.b17762.c0.d0&btm_pre=a6187.b857760.c0.d0&btm_show_id=e3a96330-bf9f-42e7-a527-9f274c00187c

https://compass.jinritemai.com/shop/chance/search-word-rank?from_page=%2Fshop%2Fchance%2Fsearch-rank-product&from=sy&btm_ppre=a6187.b857760.c0.d0&btm_pre=a6187.b779894.c0.d0&btm_show_id=5075dd62-5e48-499f-9ad6-efd6f15ef4a8

https://compass.jinritemai.com/shop/chance/search-product-rank?rank_type=4&from_page=%2Fshop%2Fchance%2Fsearch-word-rank&from=sy&btm_ppre=a6187.b779894.c0.d0&btm_pre=a6187.b17762.c0.d0&btm_show_id=15a427c1-e6b9-4d19-9b25-cda24a9fb053
结合页面上的多个排行榜首页的相关数据，结合自己店铺的行业类目，查询相关的行业新闻，具体参考下列网站：
https://www.dsb.cn/  电商派

https://www.ebrun.com/ 亿邦动力

https://www.cifnews.com/ 雨果跨境

结合上面新闻网站最新可能相关的新闻，生成相关类目的行业分析报告，结合用户的数据给用户提出一些建议，以及了解市场的方向趋势。""",
                                                 interactive=True)
                # 添加定时推送设置区域
                with gr.Accordion("⏰ 定时推送设置", open=False):
                    with gr.Row():
                        enable_schedule = gr.Checkbox(
                            label="启用定时推送",
                            value=False,
                            info="启用后将按设定间隔自动执行任务",
                            interactive=True
                        )
                    with gr.Row():
                        with gr.Column():
                            schedule_interval = gr.Slider(
                                label="推送间隔（小时）",
                                minimum=0.1,
                                maximum=24,
                                step=0.1,
                                value=1,
                                info="任务执行间隔时间，小数点表示小时分数",
                                interactive=True
                            )
                        with gr.Column():
                            schedule_title = gr.Textbox(
                                label="推送标题前缀",
                                value="深度搜索",
                                info="消息标题前缀，将与任务内容拼接",
                                interactive=True
                            )

                with gr.Row():
                    max_search_iteration_input = gr.Number(label="Max Search Iteration", value=3,
                                                           precision=0,
                                                           interactive=True)  # precision=0 确保是整数
                    max_query_per_iter_input = gr.Number(label="Max Query per Iteration", value=1,
                                                         precision=0,
                                                         interactive=True)  # precision=0 确保是整数
                with gr.Row():
                    research_button = gr.Button("▶️ Run Deep Research", variant="primary", scale=2)
                    stop_research_button = gr.Button("⏹ Stop", variant="stop", scale=1)
                    task_opt_button = gr.Button("提示词美化", variant="stop", scale=1)

                markdown_output_display = gr.Markdown(label="Research Report")
                schedule_result_text = gr.Markdown("定时任务状态将在此显示...")
                # Markdown和PPT下载部分
                with gr.Row():
                    markdown_download = gr.File(label="下载Markdown报告", interactive=False)
                with gr.Row():
                    ppt_download = gr.File(label="下载PPT报告", interactive=False)

            # Bind the stop button click event after errors_output is defined
            stop_button.click(
                fn=stop_agent,
                inputs=[],
                outputs=[stop_button, run_button],
            )

            # Run button click handler
            run_button.click(
                fn=run_with_stream,
                inputs=[
                    agent_type, llm_provider, llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url,
                    llm_api_key,
                    use_own_browser, keep_browser_open, headless, disable_security, window_w, window_h,
                    save_recording_path, save_agent_history_path, save_trace_path,  # Include the new path
                    enable_recording, task, add_infos, max_steps, use_vision, max_actions_per_step,
                    tool_calling_method, chrome_cdp, max_input_tokens
                ],
                outputs=[
                    browser_view,  # Browser view
                    final_result_output,  # Final result
                    errors_output,  # Errors
                    model_actions_output,  # Model actions
                    model_thoughts_output,  # Model thoughts
                    recording_gif,  # Latest recording
                    trace_file,  # Trace file
                    agent_history_file,  # Agent history file
                    stop_button,  # Stop button
                    run_button  # Run button
                ],
            )

            # 点击按钮生成并下载PPT的函数
            def generate_ppt_on_click(markdown_content):
                if not markdown_content:
                    return None
                try:
                    from src.utils.ppt_download import get_ppt
                    ppt_path = get_ppt(markdown_content)
                    logger.info(f"Generated PPT at: {ppt_path}")
                    # 返回文件路径和更新显示状态
                    return ppt_path, gr.update(visible=True)
                except Exception as e:
                    logger.error(f"Error generating PPT: {str(e)}")
                    return None, gr.update(visible=False)

            # Run Deep Research
            research_button.click(
                fn=run_deep_search,
                inputs=[
                    enable_schedule,
                    schedule_interval,
                    schedule_title,
                    research_task_input, max_search_iteration_input, max_query_per_iter_input, llm_provider,
                    llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key, use_vision,
                    use_own_browser, headless, chrome_cdp],
                outputs=[markdown_output_display, markdown_download, ppt_download, stop_research_button,
                         research_button]
            )

            # Bind the stop button click event
            stop_research_button.click(
                fn=stop_research_agent,
                inputs=[],
                outputs=[stop_research_button, research_button],
            )

            # Connect the task_opt_button to the optimize_prompt function
            task_opt_button.click(
                fn=optimize_prompt,
                inputs=[research_task_input, llm_provider,
                        llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key],
                outputs=[research_task_input]
            )

            # 添加定时推送设置标签页
            (
                scheduler_enabled, scheduler_interval, scheduler_task, scheduler_title,
                scheduler_iterations, scheduler_queries, scheduler_status_text,
                scheduler_next_run_text, scheduler_start_btn, scheduler_stop_btn,
                scheduler_run_once_btn, scheduler_result_text
            ) = create_scheduler_tab()

            # 绑定定时推送标签页的事件处理
            # 创建一个辅助函数来转换小时到分钟
            def convert_hours_to_minutes(llm_provider,
                                         llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key,
                                         hours, task, title, iterations, queries):
                minutes = int(float(hours) * 60)  # 将小时转换为分钟
                return start_scheduler(llm_provider,
                                       llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key, task,
                                       minutes, title, iterations, queries)

            scheduler_start_btn.click(
                fn=convert_hours_to_minutes,
                inputs=[
                    llm_provider,
                    llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key,
                    scheduler_interval,
                    scheduler_task,
                    scheduler_title,
                    scheduler_iterations,
                    scheduler_queries
                ],
                outputs=[scheduler_result_text]
            )

            scheduler_stop_btn.click(
                fn=stop_scheduler,
                inputs=[],
                outputs=[scheduler_result_text, scheduler_status_text, scheduler_next_run_text]
            )

            scheduler_run_once_btn.click(
                fn=run_push_task_once,
                inputs=[
                    llm_provider,
                    llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key,
                    scheduler_task,
                    scheduler_title,
                    scheduler_iterations,
                    scheduler_queries
                ],
                outputs=[scheduler_result_text, scheduler_status_text, scheduler_next_run_text]
            )
            with gr.TabItem("🎥 Recordings", id=7, visible=True):
                def list_recordings(save_recording_path):
                    if not os.path.exists(save_recording_path):
                        return []

                    # Get all video files
                    recordings = glob.glob(os.path.join(save_recording_path, "*.[mM][pP]4")) + glob.glob(
                        os.path.join(save_recording_path, "*.[wW][eE][bB][mM]"))

                    # Sort recordings by creation time (oldest first)
                    recordings.sort(key=os.path.getctime)

                    # Add numbering to the recordings
                    numbered_recordings = []
                    for idx, recording in enumerate(recordings, start=1):
                        filename = os.path.basename(recording)
                        numbered_recordings.append((recording, f"{idx}. {filename}"))

                    return numbered_recordings

                recordings_gallery = gr.Gallery(
                    label="Recordings",
                    columns=3,
                    height="auto",
                    object_fit="contain"
                )

                refresh_button = gr.Button("🔄 Refresh Recordings", variant="secondary")
                refresh_button.click(
                    fn=list_recordings,
                    inputs=save_recording_path,
                    outputs=recordings_gallery
                )

            with gr.TabItem("📁 UI Configuration", id=8):
                config_file_input = gr.File(
                    label="Load UI Settings from Config File",
                    file_types=[".json"],
                    interactive=True
                )
                with gr.Row():
                    load_config_button = gr.Button("Load Config", variant="primary")
                    save_config_button = gr.Button("Save UI Settings", variant="primary")

                config_status = gr.Textbox(
                    label="Status",
                    lines=2,
                    interactive=False
                )
                save_config_button.click(
                    fn=save_current_config,
                    inputs=[],  # 不需要输入参数
                    outputs=[config_status]
                )

        # Attach the callback to the LLM provider dropdown
        llm_provider.change(
            lambda provider, api_key, base_url: update_model_dropdown(provider, api_key, base_url),
            inputs=[llm_provider, llm_api_key, llm_base_url],
            outputs=llm_model_name
        )

        # Add this after defining the components
        enable_recording.change(
            lambda enabled: gr.update(interactive=enabled),
            inputs=enable_recording,
            outputs=save_recording_path
        )

        use_own_browser.change(fn=close_global_browser)
        keep_browser_open.change(fn=close_global_browser)

        scan_and_register_components(demo)
        global webui_config_manager
        all_components = webui_config_manager.get_all_components()

        load_config_button.click(
            fn=update_ui_from_config,
            inputs=[config_file_input],
            outputs=all_components + [config_status]
        )
    return demo


def main():
    parser = argparse.ArgumentParser(description="Gradio UI for Browser Agent")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="IP address to bind to")
    parser.add_argument("--port", type=int, default=7788, help="Port to listen on")
    parser.add_argument("--theme", type=str, default="Ocean", choices=theme_map.keys(), help="Theme to use for the UI")
    args = parser.parse_args()

    demo = create_ui(theme_name=args.theme)
    demo.launch(server_name=args.ip, server_port=args.port)


if __name__ == '__main__':
    main()
