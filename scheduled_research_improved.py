#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
定时调度执行深度研究任务的脚本
每小时自动运行一次deep_research方法，使用项目标准方式配置和调用
"""

import os
import sys
import logging
import asyncio
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

# 导入项目模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.utils.deep_research import deep_research
import src.utils.utils as utils
from src.utils.agent_state import AgentState

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scheduled_research.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 默认任务内容
DEFAULT_TASK = "搜索最新的人工智能技术发展趋势，特别关注大型语言模型和生成式AI的应用"

# 设置项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# 结果保存目录
RESULTS_DIR = os.path.join(PROJECT_ROOT, "tmp", "scheduled_research")
os.makedirs(RESULTS_DIR, exist_ok=True)

# 深度研究配置
MAX_SEARCH_ITERATIONS = 2  # 最大搜索迭代次数
MAX_QUERY_PER_ITER = 3     # 每次迭代的最大查询数量
USE_VISION = True          # 是否使用视觉功能
HEADLESS = True           # 是否使用无头浏览器
USE_OWN_BROWSER = False    # 不使用外部浏览器，而是自行启动一个新实例

# LLM配置
LLM_PROVIDER = "openai"  # 仍然使用openai接口格式
LLM_MODEL_NAME = "qwen-max"  # 使用阂文模型
LLM_NUM_CTX = 4000
LLM_TEMPERATURE = 0.5
LLM_BASE_URL = os.getenv("ALIBABA_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_API_KEY = os.getenv("ALIBABA_API_KEY", "sk-a144d606f37245d486e7ed61cd53c2fe")  # 使用预设的API密钥

async def run_deep_research():
    """
    运行深度研究任务
    使用webui.py中相同的方式配置和调用deep_research
    """
    try:
        # 记录开始时间
        start_time = datetime.now()
        logger.info(f"开始执行定时深度研究任务，时间：{start_time}")
        
        # 创建代理状态
        agent_state = AgentState()
        agent_state.clear_stop()
        
        # 获取LLM模型，与webui.py中相同的方式
        llm = utils.get_llm_model(
            provider=LLM_PROVIDER,
            model_name=LLM_MODEL_NAME,
            num_ctx=LLM_NUM_CTX,
            temperature=LLM_TEMPERATURE,
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
        )
        
        # 执行深度研究任务，使用自动启动的浏览器
        markdown_content, file_path = await deep_research(
            DEFAULT_TASK, 
            llm, 
            agent_state,
            max_search_iterations=MAX_SEARCH_ITERATIONS,
            max_query_num=MAX_QUERY_PER_ITER,
            use_vision=USE_VISION,
            headless=HEADLESS,
            use_own_browser=USE_OWN_BROWSER
        )
        
        # 记录结束时间和执行时长
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"深度研究任务执行完成，用时：{duration}秒")
        
        # 日志记录结果信息
        if markdown_content:
            logger.info(f"结果摘要：{markdown_content[:200]}...")
            logger.info(f"结果文件路径：{file_path}")
        else:
            logger.warning("没有获取到深度研究结果")
        
        # 将结果保存到额外的文件（保险措施）
        if markdown_content:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = os.path.join(RESULTS_DIR, f"research_results_{timestamp}.md")
            
            with open(result_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            logger.info(f"额外结果副本已保存到文件：{result_file}")
        
        return markdown_content, file_path
    except Exception as e:
        logger.error(f"深度研究任务执行失败：{str(e)}", exc_info=True)
        return f"执行错误: {str(e)}", None

def scheduled_job():
    """
    定时任务入口函数
    使用asyncio运行异步深度研究任务
    """
    logger.info("定时任务触发")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_deep_research())
        return result
    except Exception as e:
        logger.error(f"任务执行失败：{e}", exc_info=True)
        return f"Error: {str(e)}", None
    finally:
        loop.close()

def main():
    """
    主函数，设置并启动定时调度器
    """
    logger.info("定时深度研究调度器启动")
    
    # 创建调度器
    executor = ThreadPoolExecutor(max_workers=1)
    scheduler = BlockingScheduler(executors={'default': executor})
    
    # 添加定时任务，每小时执行一次
    trigger = IntervalTrigger(hours=1)
    scheduler.add_job(
        scheduled_job, 
        trigger=trigger,
        id='deep_research_job',
        name='每小时执行的深度研究任务',
        replace_existing=True
    )
    
    try:
        # 立即执行一次任务
        logger.info("立即执行一次任务...")
        try:
            scheduled_job()
        except Exception as e:
            logger.error(f"首次执行任务失败：{str(e)}", exc_info=True)
            logger.info("继续启动调度器...")
        
        # 启动调度器
        logger.info("启动定时调度器，每小时执行一次任务")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("接收到退出信号，停止调度器")
    except Exception as e:
        logger.error(f"调度器运行出错：{str(e)}", exc_info=True)
    finally:
        if scheduler.running:
            scheduler.shutdown()
        logger.info("调度器已关闭")

if __name__ == "__main__":
    main()
