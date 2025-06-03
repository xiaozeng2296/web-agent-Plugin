#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
定时调度执行深度研究任务的脚本
每小时自动运行一次deep_research方法，使用默认任务参数
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

# 导入项目模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils.deep_research import deep_research

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

# 兼容deep_research的LLM接口
class SimpleLLM:
    """兼容deep_research的LLM接口，实现所有必要方法"""
    def __init__(self):
        # 初始化LLM接口
        self.messages = []
    
    async def apredict(self, text):
        """异步预测方法"""
        return f"分析结果：{text}"
    
    def predict(self, text):
        """同步预测方法"""
        return f"分析结果：{text}"
    
    # 定义与deep_research兼容的方法    
    async def invoke(self, prompt, **kwargs):
        """提供给deep_research的invoke方法，确保返回格式兼容"""
        logger.debug(f"LLM接收到调用，提示词长度: {len(str(prompt))}")
        result = {
            "content": f"对于查询\"{prompt[:100]}...\"的分析结果：这是一个自动化分析报告，包含了相关信息的概述和总结。"
        }
        logger.debug("LLM返回结果")
        return result
    
    def bind_tools(self, *args, **kwargs):
        """绑定工具方法，无实际功能，为了兼容性"""
        logger.debug("工具绑定请求被忽略")
        pass

async def run_deep_research():
    """
    运行深度研究任务
    执行默认任务，使用简单的LLM实例
    """
    try:
        # 记录开始时间
        start_time = datetime.now()
        logger.info(f"开始执行定时深度研究任务，时间：{start_time}")
        
        # 创建简单的LLM实例
        llm = SimpleLLM()
        
        # 执行深度研究任务
        # 这里可以根据实际情况调整参数
        result = await deep_research(
            task=DEFAULT_TASK,
            llm=llm,
            use_own_browser=True,  # 使用已打开的浏览器实例
            headless=False,        # 使用有头模式方便调试
            save_dir=RESULTS_DIR,
            max_query_num=3,       # 每次迭代最多执行3个查询
            max_iter=2,           # 限制迭代次数，避免运行时间过长
            disable_security=True  # 禁用安全限制
        )
        
        # 记录结束时间和执行时长
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"深度研究任务执行完成，用时：{duration}秒")
        logger.info(f"结果摘要：{result[:200]}...")
        
        # 将结果保存到文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(RESULTS_DIR, f"research_results_{timestamp}.txt")
        
        # 处理结果可能是元组的情况
        if isinstance(result, tuple):
            result_str = str(result[0]) if result and len(result) > 0 else "无结果"
        else:
            result_str = str(result) if result else "无结果"
            
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write(result_str)
        logger.info(f"结果已保存到文件：{result_file}")
        
        return result
    except Exception as e:
        logger.error(f"深度研究任务执行失败：{str(e)}", exc_info=True)
        return None

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
    finally:
        loop.close()

def main():
    """
    主函数，设置并启动定时调度器
    """
    logger.info("定时深度研究调度器启动")
    
    # 创建调度器
    scheduler = BlockingScheduler()
    
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
