from dotenv import load_dotenv
load_dotenv()

# 标准库导入
import os
import time
import json
import glob
import asyncio
import logging
import hashlib
import zipfile
import argparse
import threading
from datetime import datetime, timedelta
from urllib.parse import quote

# 第三方库导入
from apscheduler.schedulers.background import BackgroundScheduler

# 内部模块导入
from src.utils.deep_research import deep_research
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)

import gradio as gr

from browser_use.agent.service import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import (
    BrowserContextWindowSize,
)
from src.utils.agent_state import AgentState

from src.agent.custom_agent import CustomAgent
from src.browser.custom_browser import CustomBrowser
from src.agent.custom_prompts import CustomSystemPrompt, CustomAgentMessagePrompt
from src.browser.custom_context import BrowserContextConfig
from src.controller.custom_controller import CustomController
from gradio.themes import Citrus, Default, Glass, Monochrome, Ocean, Origin, Soft, Base
from src.utils.utils import update_model_dropdown, get_latest_files, capture_screenshot, MissingAPIKeyError
from src.utils import utils
from src.utils.dingding_utils import DingTalkRobot
from src.utils.app_state import app_state

# 注意：全局变量已被移至 app_state 单例管理，请使用 app_state 提供的方法访问
# 可通过 app_state.get_browser(), app_state.get_agent(), app_state.get_scheduler() 等方法访问资源

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

def start_scheduler(research_task, interval_minutes=60, title_prefix="深度研究", search_iterations=2, query_per_iter=3):
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


# 立即执行一次推送任务
async def run_push_task_once(research_task, title_prefix="深度研究", search_iterations=2, query_per_iter=3):
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


async def execute_push_task(research_task, title_prefix="深度研究", search_iterations=2, query_per_iter=3):
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
        
        # 使用非阻塞方式更新调度器状态
        scheduler_status = {
            "last_run_time": start_time,
            "last_status": "运行中"
        }
        # app_state.update_scheduler_status(scheduler_status, blocking=False)

        # 创建代理状态
        agent_state = AgentState()
        agent_state.clear_stop()

        # 获取LLM模型 - 使用阿里云配置
        llm = utils.get_llm_model(
            provider="alibaba",
            model_name=os.getenv("ALIBABA_MODEL_NAME", "qwen-plus"),
            num_ctx=int(os.getenv("ALIBABA_CTX_SIZE", "4096")),
            temperature=float(os.getenv("ALIBABA_TEMPERATURE", "0.7")),
            base_url=os.getenv("ALIBABA_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            api_key=os.getenv("ALIBABA_API_KEY", "sk-a144d606f37245d486e7ed61cd53c2fe"),
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


async def scheduled_job(research_task, title_prefix="深度研究", search_iterations=2, query_per_iter=3, is_manual=False):
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
        
        # 获取代理状态并清除之前的停止请求
        agent_state = app_state.get_agent_state()
        agent_state.clear_stop()
        
        # 获取超时设置
        timeout_seconds = int(os.getenv("TASK_TIMEOUT", "600"))
        
        # 直接异步执行任务
        try:
            # 使用asyncio.wait_for设置超时
            result, markdown_content, file_path = await asyncio.wait_for(
                execute_push_task(
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
    try:
        agent = app_state.get_agent()
        if agent is not None:
            # Request stop
            agent.stop()
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
    """Request the research agent to stop and update UI with feedback"""
    try:
        # 获取代理状态实例并发送停止请求
        agent_state = app_state.get_agent_state()
        agent_state.request_stop()

        message = "研究代理停止请求已发送，将在下一个安全点停止"
        logger.info(f"🛑 {message}")

        # 返回UI更新
        return (
            gr.update(value="正在停止...", interactive=False),  # stop_button
            gr.update(interactive=False),  # run_button
        )
    except Exception as e:
        error_msg = f"停止代理时出错: {str(e)}"
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
    """运行标准浏览器代理

    使用 AppState 单例管理浏览器和代理实例的生命周期，确保资源正确分配和释放

    参数:
        llm: 语言模型实例
        use_own_browser: 是否使用用户自己的浏览器
        keep_browser_open: 任务完成后是否保持浏览器打开状态
        headless: 是否使用无头模式运行浏览器
        disable_security: 是否禁用浏览器安全特性
        window_w: 浏览器窗口宽度
        window_h: 浏览器窗口高度
        save_recording_path: 录制视频保存路径
        save_agent_history_path: 代理历史记录保存路径
        save_trace_path: Trace文件保存路径
        task: 代理任务描述
        max_steps: 最大执行步数
        use_vision: 是否使用视觉功能
        max_actions_per_step: 每步最大动作数
        tool_calling_method: 工具调用方式
        chrome_cdp: Chrome浏览器调试协议URL
        max_input_tokens: 最大输入令牌数

    返回:
        final_result: 最终执行结果
        errors: 错误信息
        model_actions: 模型执行动作
        model_thoughts: 模型思考过程
        trace_file: Trace文件路径
        history_file: 历史文件路径
    """
    start_time = datetime.now()
    logger.info(f"开始运行标准代理任务: {task[:50]}...")

    try:
        # 准备浏览器配置
        extra_chromium_args = ["--accept_downloads=True", f"--window-size={window_w},{window_h}"]
        cdp_url = chrome_cdp

        if use_own_browser:
            # 使用用户自己的浏览器配置
            cdp_url = os.getenv("CHROME_CDP", chrome_cdp)
            chrome_path = os.getenv("CHROME_PATH", None)
            if chrome_path == "":
                chrome_path = None
            chrome_user_data = os.getenv("CHROME_USER_DATA", None)
            if chrome_user_data:
                extra_chromium_args += [f"--user-data-dir={chrome_user_data}"]
        else:
            chrome_path = None

        # 获取或创建浏览器实例
        browser = app_state.get_browser()
        if browser is None:
            logger.info("创建新的浏览器实例")
            browser = Browser(
                config=BrowserConfig(
                    headless=headless,
                    cdp_url=cdp_url,
                    disable_security=disable_security,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=extra_chromium_args,
                )
            )
            app_state.set_browser(browser)

        # 获取或创建浏览器上下文
        browser_context = app_state.get_browser_context()
        if browser_context is None:
            logger.info("创建新的浏览器上下文")
            browser_context = await browser.new_context(
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
            app_state.set_browser_context(browser_context)

        # 获取或创建代理实例
        agent = app_state.get_agent()
        if agent is None:
            logger.info("创建新的代理实例")
            agent = Agent(
                task=task,
                llm=llm,
                use_vision=use_vision,
                browser=browser,
                browser_context=browser_context,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method,
                max_input_tokens=max_input_tokens,
                generate_gif=True
            )
            app_state.set_agent(agent)

        # 运行代理任务
        logger.info(f"开始执行代理任务，最大步数: {max_steps}")
        history = await agent.run(max_steps=max_steps)

        # 保存历史记录
        history_file = os.path.join(save_agent_history_path, f"{agent.state.agent_id}.json")
        agent.save_history(history_file)
        logger.info(f"代理历史已保存至: {history_file}")

        # 提取结果
        final_result = history.final_result()
        errors = history.errors()
        model_actions = history.model_actions()
        model_thoughts = history.model_thoughts()

        # 获取最新的trace文件
        trace_file = get_latest_files(save_trace_path)

        # 记录执行耗时
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"代理任务执行完成，耗时: {execution_time:.2f}秒")

        return final_result, errors, model_actions, model_thoughts, trace_file.get('.zip'), history_file
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"代理任务执行失败: {str(e)}\n{error_details}")
        errors = str(e) + "\n" + error_details
        return '', errors, '', '', None, None
    finally:
        # 清理代理实例
        app_state.set_agent(None)

        # 根据配置决定是否保持浏览器打开
        if not keep_browser_open:
            logger.info("关闭浏览器资源")
            browser_context = app_state.get_browser_context()
            if browser_context:
                await browser_context.close()
                app_state.set_browser_context(None)

            browser = app_state.get_browser()
            if browser:
                await browser.close()
                app_state.set_browser(None)


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
    """运行自定义浏览器代理

    使用 AppState 单例管理浏览器和代理实例的生命周期，确保资源正确分配和释放

    参数:
        llm: 语言模型实例
        use_own_browser: 是否使用用户自己的浏览器
        keep_browser_open: 任务完成后是否保持浏览器打开状态
        headless: 是否使用无头模式运行浏览器
        disable_security: 是否禁用浏览器安全特性
        window_w: 浏览器窗口宽度
        window_h: 浏览器窗口高度
        save_recording_path: 录制视频保存路径
        save_agent_history_path: 代理历史记录保存路径
        save_trace_path: Trace文件保存路径
        task: 代理任务描述
        add_infos: 附加信息
        max_steps: 最大执行步数
        use_vision: 是否使用视觉功能
        max_actions_per_step: 每步最大动作数
        tool_calling_method: 工具调用方式
        chrome_cdp: Chrome浏览器调试协议URL
        max_input_tokens: 最大输入令牌数

    返回:
        final_result: 最终执行结果
        errors: 错误信息
        model_actions: 模型执行动作
        model_thoughts: 模型思考过程
        trace_file: Trace文件路径
        history_file: 历史文件路径
    """
    start_time = datetime.now()
    logger.info(f"开始运行自定义代理任务: {task[:50]}...")

    try:
        # 准备浏览器配置
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

        # 获取或创建自定义浏览器实例
        browser = app_state.get_browser()
        cdp_condition = cdp_url and cdp_url != "" and cdp_url != None

        # 如果没有浏览器实例或CDP URL发生变化，则创建新实例
        if (browser is None) or cdp_condition:
            logger.info("创建新的自定义浏览器实例")
            browser = CustomBrowser(
                config=BrowserConfig(
                    headless=headless,
                    disable_security=disable_security,
                    cdp_url=cdp_url,
                    chrome_instance_path=chrome_path,
                    extra_chromium_args=extra_chromium_args,
                )
            )
            app_state.set_browser(browser)

        # 获取或创建浏览器上下文
        browser_context = app_state.get_browser_context()
        if browser_context is None or cdp_condition:
            logger.info("创建新的自定义浏览器上下文")
            browser_context = await browser.new_context(
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
            app_state.set_browser_context(browser_context)

        # 创建和运行代理实例
        agent = app_state.get_agent()
        if agent is None:
            logger.info("创建新的自定义代理实例")
            agent = CustomAgent(
                task=task,
                add_infos=add_infos,
                use_vision=use_vision,
                llm=llm,
                browser=browser,
                browser_context=browser_context,
                controller=controller,
                system_prompt_class=CustomSystemPrompt,
                agent_prompt_class=CustomAgentMessagePrompt,
                max_actions_per_step=max_actions_per_step,
                tool_calling_method=tool_calling_method,
                max_input_tokens=max_input_tokens,
                generate_gif=True
            )
            app_state.set_agent(agent)

        # 运行代理任务
        logger.info(f"开始执行自定义代理任务，最大步数: {max_steps}")
        history = await agent.run(max_steps=max_steps)

        # 保存代理历史
        history_file = os.path.join(save_agent_history_path, f"{agent.state.agent_id}.json")
        agent.save_history(history_file)
        logger.info(f"代理历史已保存至: {history_file}")

        # 提取结果
        final_result = history.final_result()
        errors = history.errors()
        model_actions = history.model_actions()
        model_thoughts = history.model_thoughts()

        # 获取最新的trace文件
        trace_file = get_latest_files(save_trace_path)

        # 记录执行耗时
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"自定义代理任务执行完成，耗时: {execution_time:.2f}秒")

        return final_result, errors, model_actions, model_thoughts, trace_file.get('.zip'), history_file
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"自定义代理任务执行失败: {str(e)}\n{error_details}")
        errors = str(e) + "\n" + error_details
        return '', errors, '', '', None, None
    finally:
        # 清理代理实例
        app_state.set_agent(None)

        # 根据配置决定是否保持浏览器打开
        if not keep_browser_open:
            logger.info("关闭浏览器资源")
            browser_context = app_state.get_browser_context()
            if browser_context:
                await browser_context.close()
                app_state.set_browser_context(None)

            browser = app_state.get_browser()
            if browser:
                await browser.close()
                app_state.set_browser(None)


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
    """带流式更新的代理运行方法

    使用 AppState 单例管理浏览器和代理实例的生命周期，提供实时屏幕更新
    """
    logger.info(f"开始流式运行代理任务: {task[:50]}...")

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
                    # 使用 app_state 获取浏览器上下文进行截图
                    browser_context = app_state.get_browser_context()
                    encoded_screenshot = await capture_screenshot(browser_context)
                    if encoded_screenshot is not None:
                        html_content = f'<img src="data:image/jpeg;base64,{encoded_screenshot}" style="width:{stream_vw}vw; height:{stream_vh}vh ; border:1px solid #ccc;">'
                    else:
                        html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>等待浏览器会话初始化...</h1>"
                except Exception as e:
                    logger.error(f"浏览器截图错误: {str(e)}")
                    html_content = f"<h1 style='width:{stream_vw}vw; height:{stream_vh}vh'>等待浏览器会话初始化...</h1>"

                # 使用 app_state 检查代理是否已经停止
                agent = app_state.get_agent()
                if agent and agent.state.stopped:
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
    """关闭全局浏览器和浏览器上下文并释放资源"""
    browser_context = app_state.get_browser_context()
    if browser_context:
        await browser_context.close()
        app_state.set_browser_context(None)

    browser = app_state.get_browser()
    if browser:
        await browser.close()
        app_state.set_browser(None)

    logger.info("全局浏览器资源已释放")


async def run_deep_search(research_task, max_search_iteration_input, max_query_per_iter_input, llm_provider,
                          llm_model_name, llm_num_ctx, llm_temperature, llm_base_url, llm_api_key, use_vision,
                          use_own_browser, headless, chrome_cdp):
    """运行深度搜索研究任务"""
    from src.utils.deep_research import deep_research

    # 获取代理状态并清除之前的停止请求
    agent_state = app_state.get_agent_state()
    agent_state.clear_stop()

    llm = utils.get_llm_model(
        provider=llm_provider,
        model_name=llm_model_name,
        num_ctx=llm_num_ctx,
        temperature=llm_temperature,
        base_url=llm_base_url,
        api_key=llm_api_key,
    )
    markdown_content, file_path = await deep_research(research_task, llm, agent_state,
                                                      max_search_iterations=max_search_iteration_input,
                                                      max_query_num=max_query_per_iter_input,
                                                      use_vision=use_vision,
                                                      headless=headless,
                                                      use_own_browser=use_own_browser,
                                                      chrome_cdp=chrome_cdp
                                                      )

    return markdown_content, file_path, gr.update(value="Stop", interactive=True), gr.update(interactive=True)


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
                markdown_output_display = gr.Markdown(label="Research Report")
                markdown_download = gr.File(label="Download Research Report")

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

            # Run Deep Research
            research_button.click(
                fn=run_deep_search,
                inputs=[research_task_input, max_search_iteration_input, max_query_per_iter_input, llm_provider,
                        llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key, use_vision,
                        use_own_browser, headless, chrome_cdp],
                outputs=[markdown_output_display, markdown_download, stop_research_button, research_button]
            )
            # Bind the stop button click event after errors_output is defined
            stop_research_button.click(
                fn=stop_research_agent,
                inputs=[],
                outputs=[stop_research_button, research_button],
            )

            # 定时推送设置标签页
            with gr.TabItem("⏰ 定时推送设置", id=6):
                with gr.Row():
                    with gr.Column():
                        # 基本设置
                        scheduler_enabled = gr.Checkbox(label="启用定时推送", value=False,
                                                        info="启用后将按设定间隔自动执行任务")
                        scheduler_interval = gr.Slider(label="推送间隔（分钟）", minimum=1, maximum=1440, step=1,
                                                       value=60,
                                                       info="任务执行间隔时间，整数分钟，范围 1分钟-24小时(1440分钟)")
                        scheduler_task = gr.Textbox(label="定时任务内容", lines=4,
                                                    value="搜索最新的人工智能技术发展趋势，特别关注大型语言模型和生成式AI的应用",
                                                    info="研究任务内容描述")

                    with gr.Column():
                        # 高级设置
                        scheduler_title = gr.Textbox(label="推送标题前缀", value="深度研究",
                                                     info="消息标题前缀，将与任务内容拼接")
                        with gr.Row():
                            scheduler_iterations = gr.Number(label="最大搜索迭代次数", value=2, minimum=1, maximum=5,
                                                             step=1, precision=0,
                                                             info="每次任务执行的最大搜索迭代次数")
                            scheduler_queries = gr.Number(label="每迭代查询数", value=3, minimum=1, maximum=5, step=1,
                                                          precision=0,
                                                          info="每次迭代的最大查询数量")

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

                # 绑定按钮事件
                def update_scheduler_status():
                    """
                    返回调度器状态显示信息（简化版，不使用共享状态）

                    返回:
                        tuple: (状态文本, 下次执行时间文本)
                    """
                    # 不再查询app_state的状态，避免死锁风险
                    scheduler = app_state._scheduler  # 直接访问属性，避免使用锁
                    
                    # 检查调度器是否运行
                    is_running = scheduler is not None and hasattr(scheduler, 'running') and scheduler.running
                    status = "运行中" if is_running else "未启动"
                    
                    # 获取下次执行时间
                    next_run_text = "无排程"
                    if is_running and scheduler.get_jobs():
                        job = scheduler.get_jobs()[0]
                        if job and job.next_run_time:
                            next_run_text = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 生成状态文本
                    status_text = f"调度器状态: {status}"
                    next_run_md = f"下次执行时间: {next_run_text}"
                    
                    return status_text, next_run_md

                # 界面加载时初始化调度器状态显示
                def init_scheduler_display():
                    """
                    界面加载时初始化调度器状态显示

                    返回:
                        tuple: (检测结果消息, 状态文本, 下次执行时间文本)
                    """
                    # 检测环境变量和必要依赖
                    missing_config = []
                    if not os.environ.get('DINGTALK_WEBHOOK_URL'):
                        missing_config.append('钩子URL')
                    if not os.environ.get('DINGTALK_SECRET'):
                        missing_config.append('安全密钥')

                    if missing_config:
                        return f"警告: 缺少钩子配置: {', '.join(missing_config)}，请在环境变量中添加", *update_scheduler_status()

                    # 回显调度器状态
                    status, next_run = update_scheduler_status()
                    return "已准备就绪，可启动调度器", status, next_run

                # 启动时初始化调度器状态
                status_text, next_run_text = update_scheduler_status()
                scheduler_status_text.value = status_text
                scheduler_next_run_text.value = next_run_text

                # 检查配置并设置初始状态
                init_result, status_text, next_run_text = init_scheduler_display()
                scheduler_result_text.value = init_result
                scheduler_status_text.value = status_text
                scheduler_next_run_text.value = next_run_text

                # 启动调度器函数 - 安全版本，避免可能的死锁风险
                def ui_start_scheduler(enabled, task, interval, title, iterations, queries):
                    if not enabled:
                        return "请先勾选启用定时推送选项", "调度器状态: 未启动", "下次执行时间: 无排程"

                    if not task or task.strip() == "":
                        return "请输入有效的任务内容", "调度器状态: 未启动", "下次执行时间: 无排程"
                    
                    # 计算时间间隔（分钟）
                    minutes = float(interval) * 60  # 将小时转换为分钟
                    
                    try:
                        logger.info(f"准备启动调度器: 间隔 {minutes} 分钟, 任务: {task}")
                        
                        # 调用启动调度器函数
                        result = start_scheduler(
                            research_task=task,
                            interval_minutes=minutes,
                            title_prefix=title,
                            search_iterations=int(iterations),
                            query_per_iter=int(queries)
                        )
                        
                        # 直接计算下次执行时间，而不是通过状态查询
                        next_run_time = datetime.now() + timedelta(minutes=minutes)
                        next_run_text = next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                        
                        # 返回结果和状态信息
                        return result, "调度器状态: 运行中", f"下次执行时间: {next_run_text}"
                    except Exception as e:
                        logger.error(f"启动调度器异常: {str(e)}", exc_info=True)
                        return f"启动调度器失败: {str(e)}", "调度器状态: 异常", "下次执行时间: 无排程"

                # 停止调度器函数 - 安全版本，避免可能的死锁风险
                def ui_stop_scheduler():
                    try:
                        logger.info("用户触发停止调度器")
                        result = stop_scheduler()
                        # 直接返回状态，而不是通过update_scheduler_status查询
                        return result, "调度器状态: 未启动", "下次执行时间: 无排程"
                    except Exception as e:
                        logger.error(f"停止调度器异常: {str(e)}", exc_info=True)
                        return f"停止调度器失败: {str(e)}", "调度器状态: 异常", "下次执行时间: 无排程"

                # 立即执行一次函数（异步版本）- 安全版本，避免可能的死锁风险
                async def ui_run_once(task, title, iterations, queries):
                    if not task or task.strip() == "":
                        return "请输入有效的任务内容", "调度器状态: 未知", "下次执行时间: 无排程"
                    
                    logger.info(f"用户触发立即执行按钮: {task}")
                    
                    try:
                        # 调用异步执行一次函数
                        result_msg = await execute_push_task(
                            research_task=task,
                            title_prefix=title,
                            search_iterations=int(iterations),
                            query_per_iter=int(queries)
                        )
                        
                        # 直接构造状态文本，避免查询状态
                        scheduler = app_state._scheduler
                        is_running = scheduler is not None and hasattr(scheduler, 'running') and scheduler.running
                        
                        if is_running and scheduler.get_jobs():
                            job = scheduler.get_jobs()[0]
                            if job and job.next_run_time:
                                next_run_text = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                                return result_msg, "调度器状态: 运行中", f"下次执行时间: {next_run_text}"
                        
                        # 如果没有启动调度器或无法获取下次执行时间
                        return result_msg, "调度器状态: 未启动", "下次执行时间: 无排程"
                    except Exception as e:
                        error_msg = f"执行异常: {str(e)[:100]}"
                        logger.error(error_msg, exc_info=True)
                        return error_msg, f"执行状态: 失败", "执行异常"

                # 绑定按钮事件
                scheduler_start_btn.click(
                    fn=ui_start_scheduler,
                    inputs=[scheduler_enabled, scheduler_task, scheduler_interval,
                            scheduler_title, scheduler_iterations, scheduler_queries],
                    outputs=[scheduler_result_text, scheduler_status_text, scheduler_next_run_text]
                )

                scheduler_stop_btn.click(
                    fn=ui_stop_scheduler,
                    inputs=[],
                    outputs=[scheduler_result_text, scheduler_status_text, scheduler_next_run_text]
                )

                # 绑定立即执行按钮 - 使用异步回调函数
                scheduler_run_once_btn.click(
                    fn=ui_run_once,  # 异步回调函数
                    inputs=[scheduler_task, scheduler_title, scheduler_iterations, scheduler_queries],
                    outputs=[scheduler_result_text, scheduler_status_text, scheduler_next_run_text],
                    api_name="run_task_once"  # 添加API名称便于调试
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