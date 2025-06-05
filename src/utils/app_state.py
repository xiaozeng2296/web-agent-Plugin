"""
AppState 模块 - 应用全局状态管理
提供统一的应用状态管理接口，使用单例模式确保全局状态的一致性
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional

from src.utils.agent_state import AgentState

logger = logging.getLogger(__name__)

class AppState:
    """
    全局应用状态管理类，采用单例模式
    管理所有全局资源和状态，提供线程安全的访问控制
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AppState, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        logger.info("初始化应用状态管理器")
        self._lock = threading.Lock()
        
        # 浏览器相关资源
        self._browser = None
        self._browser_context = None
        
        # 代理实例
        self._agent = None
        
        # 调度器相关
        self._scheduler = None
        self._scheduler_status = {
            "running": False,
            "next_run_time": None,
            "last_run_time": None,
            "last_status": "",
            "interval_hours": 1,
        }
        
        # 代理状态（本身是单例，但统一管理）
        self._agent_state = AgentState()
        
        # 资源使用统计
        self._resource_stats = {
            "browser_created_time": None,
            "browser_usage_count": 0,
            "last_activity_time": datetime.now(),
        }
        
        # 初始化完成标志
        self._initialized = True
        logger.info("应用状态管理器初始化完成")

    # 浏览器相关方法
    def get_browser(self):
        """获取全局浏览器实例"""
        with self._lock:
            return self._browser
    
    def set_browser(self, browser):
        """设置全局浏览器实例"""
        with self._lock:
            self._browser = browser
            if browser is not None:
                self._resource_stats["browser_created_time"] = datetime.now()
                self._resource_stats["browser_usage_count"] += 1
            self._update_activity_time()
            logger.debug("浏览器实例已更新")
    
    def get_browser_context(self):
        """获取全局浏览器上下文"""
        with self._lock:
            return self._browser_context
    
    def set_browser_context(self, context):
        """设置全局浏览器上下文"""
        with self._lock:
            self._browser_context = context
            self._update_activity_time()
            logger.debug("浏览器上下文已更新")

    # 代理相关方法
    def get_agent(self):
        """获取全局代理实例"""
        with self._lock:
            return self._agent
    
    def set_agent(self, agent):
        """设置全局代理实例"""
        with self._lock:
            self._agent = agent
            self._update_activity_time()
            logger.debug("代理实例已更新")
    
    def get_agent_state(self):
        """获取代理状态"""
        return self._agent_state
    
    # 调度器相关方法
    def get_scheduler(self):
        """获取全局调度器实例"""
        with self._lock:
            return self._scheduler
    
    def set_scheduler(self, scheduler):
        """设置全局调度器实例"""
        with self._lock:
            self._scheduler = scheduler
            self._update_scheduler_status()
            self._update_activity_time()
            logger.debug("调度器实例已更新")
    
    def get_scheduler_status(self) -> Dict:
        """获取调度器状态"""
        with self._lock:
            return self._scheduler_status.copy()
    
    def update_scheduler_status(self, status_update: Dict):
        """更新调度器状态"""
        with self._lock:
            self._scheduler_status.update(status_update)
            self._update_activity_time()
            logger.debug(f"调度器状态已更新: {status_update}")
    
    def _update_scheduler_status(self):
        """根据当前调度器更新状态信息"""
        with self._lock:
            if self._scheduler and hasattr(self._scheduler, "running"):
                self._scheduler_status["running"] = self._scheduler.running
                
                # 获取下次执行时间
                if self._scheduler.running and len(self._scheduler.get_jobs()) > 0:
                    job = self._scheduler.get_jobs()[0]
                    if job and job.next_run_time:
                        self._scheduler_status["next_run_time"] = job.next_run_time
    
    # 资源管理和状态监控
    def get_resource_stats(self) -> Dict:
        """获取资源使用统计"""
        with self._lock:
            return self._resource_stats.copy()
    
    def _update_activity_time(self):
        """更新最后活动时间"""
        with self._lock:
            self._resource_stats["last_activity_time"] = datetime.now()
    
    def clear_all_resources(self):
        """清理所有资源引用（不执行关闭操作）"""
        with self._lock:
            self._browser = None
            self._browser_context = None
            self._agent = None
            self._scheduler = None
            self._scheduler_status["running"] = False
            logger.info("已清理所有资源引用")

    def __str__(self):
        """返回状态概览"""
        with self._lock:
            browser_status = "已初始化" if self._browser else "未初始化"
            agent_status = "已初始化" if self._agent else "未初始化"
            scheduler_status = "运行中" if self._scheduler_status["running"] else "已停止"
            
            return (f"应用状态: 浏览器[{browser_status}], "
                   f"代理[{agent_status}], 调度器[{scheduler_status}]")


# 导出单例实例，方便直接导入使用
app_state = AppState()
