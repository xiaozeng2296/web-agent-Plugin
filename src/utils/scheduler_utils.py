#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调度工具类，提供方法级别的周期调度功能
"""

import logging
import threading
import functools
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union, Tuple

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)


class SchedulerManager:
    """
    调度管理器，用于创建和管理各种定时任务
    
    特点：
    1. 支持多种调度类型：间隔调度、Cron调度、一次性调度
    2. 自动管理调度器生命周期
    3. 提供任务状态查询和管理
    4. 支持异步和同步任务
    5. 完善的异常处理和日志记录
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SchedulerManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化调度管理器"""
        self._scheduler = None
        self._jobs = {}  # 存储所有作业的引用
        self._job_status = {}  # 存储作业状态信息
        self._initialized = False
        self._init_scheduler()

    def _init_scheduler(self):
        """初始化调度器"""
        if self._initialized:
            return

        try:
            # 创建一个带有线程池的后台调度器
            self._scheduler = BackgroundScheduler(
                jobstores={
                    'default': MemoryJobStore()  # 使用内存存储作业
                },
                executors={
                    'default': ThreadPoolExecutor(max_workers=20)  # 最多20个线程并发执行
                },
                job_defaults={
                    'coalesce': True,  # 合并错过的执行
                    'max_instances': 3,  # 同一个作业最多同时运行的实例数
                    'misfire_grace_time': 60  # 错过执行的宽限时间（秒）
                }
            )

            # 启动调度器
            self._scheduler.start()
            self._initialized = True
            logger.info("调度管理器初始化成功")

            # 注册关闭钩子
            import atexit
            atexit.register(self.shutdown)

        except Exception as e:
            logger.error(f"调度管理器初始化失败: {str(e)}")
            raise

    def shutdown(self, wait=True):
        """关闭调度器
        
        参数:
            wait (bool): 是否等待所有作业完成再关闭
        """
        if self._scheduler and self._initialized:
            try:
                self._scheduler.shutdown(wait=wait)
                self._initialized = False
                logger.info("调度管理器已关闭")
            except Exception as e:
                logger.error(f"关闭调度管理器时发生异常: {str(e)}")

    def _job_listener(self, event):
        """作业执行监听器，用于记录作业状态"""
        job_id = event.job_id
        if job_id not in self._job_status:
            self._job_status[job_id] = {}

        if event.code == 'executed':
            self._job_status[job_id].update({
                'last_run_time': datetime.now(),
                'last_status': 'success',
                'last_result': getattr(event, 'retval', None),
                'error': None
            })
            logger.info(f"作业 {job_id} 执行成功")

        elif event.code == 'error':
            error_msg = str(getattr(event, 'exception', '未知异常'))
            self._job_status[job_id].update({
                'last_run_time': datetime.now(),
                'last_status': 'error',
                'error': error_msg
            })
            logger.error(f"作业 {job_id} 执行失败: {error_msg}")

    def add_job(self, func: Callable,
                trigger: str = 'interval',
                job_id: Optional[str] = None,
                args: list = None,
                kwargs: dict = None,
                **trigger_args) -> str:
        """添加作业
        
        参数:
            func (Callable): 要调度的函数
            trigger (str): 触发器类型，支持 'interval'(间隔)、'cron'(定时)、'date'(一次性)
            job_id (str, optional): 作业ID，如果不提供则自动生成
            **trigger_args: 触发器参数，根据触发器类型而不同
                - interval: seconds, minutes, hours, days, weeks
                - cron: year, month, day, week, day_of_week, hour, minute, second
                - date: run_date (datetime 或 字符串)
                
        返回:
            str: 作业ID
        """
        if not self._initialized:
            self._init_scheduler()

        if job_id is None:
            # 使用函数名和时间戳生成唯一ID
            job_id = f"{func.__name__}_{int(datetime.now().timestamp())}"

        try:
            # 包装函数，添加异常处理和日志记录
            @functools.wraps(func)
            def job_wrapper(*args, **kwargs):
                start_time = datetime.now()
                logger.info(f"作业 {job_id} 开始执行，时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                try:
                    result = func(*args, **kwargs)
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    logger.info(f"作业 {job_id} 执行完成，耗时: {duration:.2f}秒")
                    return result
                except Exception as e:
                    logger.error(f"作业 {job_id} 执行异常: {str(e)}", exc_info=True)
                    raise

            # 准备任务参数
            args = args or []
            kwargs = kwargs or {}

            # 根据触发器类型创建不同的触发器
            if trigger == 'interval':
                job = self._scheduler.add_job(
                    job_wrapper,
                    IntervalTrigger(**trigger_args),
                    id=job_id,
                    name=getattr(func, '__name__', 'unnamed_job'),
                    args=args,
                    kwargs=kwargs,
                    replace_existing=True
                )
            elif trigger == 'cron':
                job = self._scheduler.add_job(
                    job_wrapper,
                    CronTrigger(**trigger_args),
                    id=job_id,
                    name=getattr(func, '__name__', 'unnamed_job'),
                    args=args,
                    kwargs=kwargs,
                    replace_existing=True
                )
            elif trigger == 'date':
                job = self._scheduler.add_job(
                    job_wrapper,
                    DateTrigger(**trigger_args),
                    id=job_id,
                    name=getattr(func, '__name__', 'unnamed_job'),
                    args=args,
                    kwargs=kwargs,
                    replace_existing=True
                )
            else:
                raise ValueError(f"不支持的触发器类型: {trigger}")

            # 存储作业引用
            self._jobs[job_id] = job

            # 初始化作业状态
            self._job_status[job_id] = {
                'created_time': datetime.now(),
                'last_run_time': None,
                'next_run_time': job.next_run_time,
                'last_status': 'pending',
                'error': None
            }

            logger.info(f"已添加作业 {job_id}, 下次执行时间: {job.next_run_time}")
            return job_id

        except Exception as e:
            logger.error(f"添加作业失败: {str(e)}")
            raise

    def remove_job(self, job_id: str) -> bool:
        """移除作业
        
        参数:
            job_id (str): 要移除的作业ID
            
        返回:
            bool: 是否成功移除
        """
        if not self._initialized or job_id not in self._jobs:
            logger.warning(f"作业 {job_id} 不存在或调度器未初始化")
            return False

        try:
            # 从调度器中移除作业
            self._scheduler.remove_job(job_id)

            # 从本地缓存中移除
            if job_id in self._jobs:
                del self._jobs[job_id]

            # 更新状态，但保留历史记录
            if job_id in self._job_status:
                self._job_status[job_id]['last_status'] = 'removed'

            logger.info(f"已成功移除作业 {job_id}")
            return True

        except Exception as e:
            logger.error(f"移除作业 {job_id} 失败: {str(e)}")
            return False

    def pause_job(self, job_id: str) -> bool:
        """暂停作业
        
        参数:
            job_id (str): 要暂停的作业ID
            
        返回:
            bool: 是否成功暂停
        """
        if not self._initialized or job_id not in self._jobs:
            logger.warning(f"作业 {job_id} 不存在或调度器未初始化")
            return False

        try:
            self._scheduler.pause_job(job_id)

            # 更新状态
            if job_id in self._job_status:
                self._job_status[job_id]['last_status'] = 'paused'

            logger.info(f"已暂停作业 {job_id}")
            return True

        except Exception as e:
            logger.error(f"暂停作业 {job_id} 失败: {str(e)}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """恢复作业
        
        参数:
            job_id (str): 要恢复的作业ID
            
        返回:
            bool: 是否成功恢复
        """
        if not self._initialized or job_id not in self._jobs:
            logger.warning(f"作业 {job_id} 不存在或调度器未初始化")
            return False

        try:
            self._scheduler.resume_job(job_id)

            # 更新状态
            if job_id in self._job_status:
                self._job_status[job_id]['last_status'] = 'resumed'
                job = self._scheduler.get_job(job_id)
                if job:
                    self._job_status[job_id]['next_run_time'] = job.next_run_time

            logger.info(f"已恢复作业 {job_id}")
            return True

        except Exception as e:
            logger.error(f"恢复作业 {job_id} 失败: {str(e)}")
            return False

    def get_job_status(self, job_id: str) -> Dict:
        """获取作业状态
        
        参数:
            job_id (str): 作业ID
            
        返回:
            Dict: 作业状态信息
        """
        if job_id not in self._job_status:
            return {"error": f"作业 {job_id} 不存在"}

        # 获取最新的下次执行时间
        status = dict(self._job_status[job_id])  # 复制一份
        try:
            job = self._scheduler.get_job(job_id)
            if job:
                status["next_run_time"] = job.next_run_time
            else:
                status["next_run_time"] = None
        except Exception:
            pass

        return status

    def get_all_jobs(self) -> Dict[str, Dict]:
        """获取所有作业及其状态
        
        返回:
            Dict[str, Dict]: 作业ID与状态信息的映射
        """
        result = {}
        for job_id in self._jobs.keys():
            result[job_id] = self.get_job_status(job_id)
        return result

    def modify_job(self, job_id: str, **kwargs) -> bool:
        """修改作业配置
        
        参数:
            job_id (str): 作业ID
            **kwargs: 要修改的参数，可以包含 trigger_type 和触发器参数
            
        返回:
            bool: 是否成功修改
        """
        if not self._initialized or job_id not in self._jobs:
            logger.warning(f"作业 {job_id} 不存在或调度器未初始化")
            return False

        try:
            # 如果指定了新的触发器类型
            trigger_type = kwargs.pop('trigger_type', None)
            if trigger_type:
                # 创建新的触发器
                if trigger_type == 'interval':
                    trigger = IntervalTrigger(**kwargs)
                elif trigger_type == 'cron':
                    trigger = CronTrigger(**kwargs)
                elif trigger_type == 'date':
                    trigger = DateTrigger(**kwargs)
                else:
                    raise ValueError(f"不支持的触发器类型: {trigger_type}")

                # 更新触发器
                self._scheduler.reschedule_job(job_id, trigger=trigger)
            else:
                # 更新其他参数
                self._scheduler.modify_job(job_id, **kwargs)

            # 更新状态
            job = self._scheduler.get_job(job_id)
            if job and job_id in self._job_status:
                self._job_status[job_id]['next_run_time'] = job.next_run_time
                self._job_status[job_id]['last_status'] = 'modified'

            logger.info(f"已修改作业 {job_id} 配置")
            return True

        except Exception as e:
            logger.error(f"修改作业 {job_id} 失败: {str(e)}")
            return False

    def execute_job_now(self, job_id: str) -> bool:
        """立即执行指定作业
        
        参数:
            job_id (str): 作业ID
            
        返回:
            bool: 是否成功触发执行
        """
        if not self._initialized or job_id not in self._jobs:
            logger.warning(f"作业 {job_id} 不存在或调度器未初始化")
            return False

        try:
            # APScheduler 提供了立即执行指定作业的方法
            self._scheduler.add_job(
                func=self._jobs[job_id].func,
                trigger='date',  # 使用日期触发器，设置为立即执行
                run_date=datetime.now(),
                id=f"{job_id}_immediate_{int(datetime.now().timestamp())}",
                name=f"immediate_{self._jobs[job_id].name}",
                replace_existing=False
            )

            logger.info(f"触发作业 {job_id} 立即执行")
            return True

        except Exception as e:
            logger.error(f"触发作业 {job_id} 立即执行失败: {str(e)}")
            return False

    def add_async_job(self, async_func: Callable,
                      trigger: str = 'interval',
                      job_id: Optional[str] = None,
                      args: list = None,
                      kwargs: dict = None,
                      **trigger_args) -> str:
        """添加异步函数作业
        
        参数:
            async_func (Callable): 要调度的异步函数
            trigger (str): 触发器类型，支持 'interval'、'cron'、'date'
            job_id (str, optional): 作业ID，如果不提供则自动生成
            **trigger_args: 触发器参数
            
        返回:
            str: 作业ID
        """
        if not self._initialized:
            self._init_scheduler()

        # 检查是否是异步函数
        import asyncio
        import inspect
        if not inspect.iscoroutinefunction(async_func):
            raise ValueError("提供的函数不是异步函数。请使用 async def 定义的函数")

        if job_id is None:
            # 使用函数名和时间戳生成唯一ID
            job_id = f"{async_func.__name__}_async_{int(datetime.now().timestamp())}"

        try:
            # 包装异步函数，注意这不是异步函数，而是运行异步事件循环的同步函数
            @functools.wraps(async_func)
            def async_job_wrapper(*args, **kwargs):
                start_time = datetime.now()
                logger.info(f"异步作业 {job_id} 开始执行，时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

                try:
                    # 创建新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    # 执行异步函数
                    result = loop.run_until_complete(async_func(*args, **kwargs))

                    # 关闭事件循环
                    loop.close()

                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    logger.info(f"异步作业 {job_id} 执行完成，耗时: {duration:.2f}秒")
                    return result

                except Exception as e:
                    logger.error(f"异步作业 {job_id} 执行异常: {str(e)}", exc_info=True)
                    if 'loop' in locals() and loop.is_running():
                        loop.close()
                    raise

            # 调用常规的添加作业方法，传入包装后的同步函数
            return self.add_job(async_job_wrapper, trigger, job_id, args=args, kwargs=kwargs, **trigger_args)

        except Exception as e:
            logger.error(f"添加异步作业失败: {str(e)}")
            raise

    def add_job_with_timeout(self, func: Callable,
                             timeout_seconds: int,
                             trigger: str = 'interval',
                             job_id: Optional[str] = None,
                             args: list = None,
                             kwargs: dict = None,
                             **trigger_args) -> str:
        """添加带超时控制的作业
        
        参数:
            func (Callable): 要调度的函数
            timeout_seconds (int): 超时时间（秒）
            trigger (str): 触发器类型
            job_id (str, optional): 作业ID
            **trigger_args: 触发器参数
            
        返回:
            str: 作业ID
        """
        if not self._initialized:
            self._init_scheduler()

        if job_id is None:
            # 使用函数名和时间戳生成唯一ID
            job_id = f"{func.__name__}_timeout_{int(datetime.now().timestamp())}"

        try:
            # 包装函数，添加超时控制
            @functools.wraps(func)
            def timeout_wrapper(*args, **kwargs):
                import signal
                import threading

                result = None
                error = None
                completed = threading.Event()

                # 定义实际执行函数的线程
                def target_func():
                    nonlocal result, error
                    try:
                        start_time = datetime.now()
                        logger.info(f"作业 {job_id} 开始执行，时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
                        result = func(*args, **kwargs)
                        end_time = datetime.now()
                        duration = (end_time - start_time).total_seconds()
                        logger.info(f"作业 {job_id} 执行完成，耗时: {duration:.2f}秒")
                    except Exception as e:
                        error = e
                        logger.error(f"作业 {job_id} 执行异常: {str(e)}", exc_info=True)
                    finally:
                        completed.set()

                # 启动执行线程
                thread = threading.Thread(target=target_func)
                thread.daemon = True  # 允许程序退出时线程也随之退出
                thread.start()

                # 等待函数完成或超时
                if not completed.wait(timeout=timeout_seconds):
                    logger.error(f"作业 {job_id} 执行超时（超过 {timeout_seconds} 秒）")
                    # 注意：线程仍将继续运行，但我们不再等待它
                    raise TimeoutError(f"作业执行超过 {timeout_seconds} 秒")

                # 如果有异常，重新抛出
                if error is not None:
                    raise error

                return result

            # 调用常规的添加作业方法，传入包装后的函数
            return self.add_job(timeout_wrapper, trigger, job_id, args=args, kwargs=kwargs, **trigger_args)

        except Exception as e:
            logger.error(f"添加超时作业失败: {str(e)}")
            raise

    def add_async_job_with_timeout(self, async_func: Callable,
                                   timeout_seconds: int,
                                   trigger: str = 'interval',
                                   job_id: Optional[str] = None,
                                   args: list = None,
                                   kwargs: dict = None,
                                   **trigger_args) -> str:
        """添加带超时控制的异步作业
        
        参数:
            async_func (Callable): 要调度的异步函数
            timeout_seconds (int): 超时时间（秒）
            trigger (str): 触发器类型
            job_id (str, optional): 作业ID
            **trigger_args: 触发器参数
            
        返回:
            str: 作业ID
        """
        import asyncio
        import inspect

        if not inspect.iscoroutinefunction(async_func):
            raise ValueError("提供的函数不是异步函数")

        if job_id is None:
            # 使用函数名和时间戳生成唯一ID
            job_id = f"{async_func.__name__}_async_timeout_{int(datetime.now().timestamp())}"

        try:
            # 包装异步函数，添加超时控制
            @functools.wraps(async_func)
            def async_timeout_wrapper(*args, **kwargs):
                start_time = datetime.now()
                logger.info(f"异步作业 {job_id} 开始执行，时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

                try:
                    # 创建新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    # 使用 asyncio.wait_for 添加超时
                    coro = async_func(*args, **kwargs)
                    result = loop.run_until_complete(
                        asyncio.wait_for(coro, timeout=timeout_seconds)
                    )

                    # 关闭事件循环
                    loop.close()

                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    logger.info(f"异步作业 {job_id} 执行完成，耗时: {duration:.2f}秒")
                    return result

                except asyncio.TimeoutError:
                    logger.error(f"异步作业 {job_id} 执行超时（超过 {timeout_seconds} 秒）")
                    # 关闭事件循环
                    if 'loop' in locals() and loop.is_running():
                        loop.close()
                    raise TimeoutError(f"异步作业执行超过 {timeout_seconds} 秒")

                except Exception as e:
                    logger.error(f"异步作业 {job_id} 执行异常: {str(e)}", exc_info=True)
                    # 关闭事件循环
                    if 'loop' in locals() and loop.is_running():
                        loop.close()
                    raise

            # 调用常规的添加作业方法，传入包装后的函数
            return self.add_job(async_timeout_wrapper, trigger, job_id, args=args, kwargs=kwargs, **trigger_args)

        except Exception as e:
            logger.error(f"添加异步超时作业失败: {str(e)}")
            raise

    # 实现上下文管理器接口
    def __enter__(self):
        """上下文管理器入口"""
        if not self._initialized:
            self._init_scheduler()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，关闭调度器"""
        self.shutdown(wait=True)
        return False  # 允许异常传递


# 使用示例

def example_usage():
    """调度工具类的使用示例"""

    # 例子异步函数
    async def async_task(name="异步任务"):
        import asyncio
        logger.info(f"执行异步任务: {name}")
        await asyncio.sleep(2)  # 模拟异步工作
        logger.info(f"异步任务 {name} 完成")
        return f"{name} 完成了"

    # 1. 基本用法 - 获取调度器实例
    scheduler = SchedulerManager()

    # 4. 添加一个异步任务
    async_job_id = scheduler.add_async_job(
        async_func=async_task,
        trigger='interval',
        seconds=2,
        args=[],
        kwargs={"name": "异步定时任务"}
    )
    # 6. 查看任务状态
    status = scheduler.get_job_status(async_job_id)
    logger.info(f"任务状态: {status}")

    # 7. 立即执行一个任务
    scheduler.execute_job_now(async_job_id)
    logger.info("调度结束")


def example_with_context_manager():
    """使用上下文管理器的示例"""

    def task():
        logger.info("执行了任务")

    # 使用 with 语句自动管理调度器生命周期
    with SchedulerManager() as scheduler:
        scheduler.add_job(func=task, trigger='interval', seconds=5)

        # 主程序可以继续运行
        import time
        time.sleep(20)

    # with 语句结束时会自动关闭调度器
    logger.info("调度器已自动关闭")


# 如果直接运行此文件，执行示例代码
if __name__ == "__main__":
    # 配置日志
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行示例
    example_usage()
    # example_with_context_manager()
