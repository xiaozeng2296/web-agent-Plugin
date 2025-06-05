"""
Web Agent UI 主模块

重构后的WebUI模块，使用模块化设计替代原有的全局变量和大型函数。
使用app_state单例管理全局资源，包括浏览器、代理和调度器。
"""

import logging

from dotenv import load_dotenv

load_dotenv()
import argparse

# 导入APScheduler相关模块

logger = logging.getLogger(__name__)

from src.utils.app_state import app_state

# 导入UI组件模块
from src.ui.ui_builder import create_ui

# 调度器关闭钩子函数
def shutdown_scheduler():
    """
    在程序退出时关闭调度器
    """
    scheduler = app_state.get_scheduler()
    if scheduler and scheduler.running:
        logger.info("程序退出，关闭调度器")

# 注册退出钩子
import atexit
atexit.register(shutdown_scheduler)


def main():
    """
    主函数，解析命令行参数并启动WebUI
    """
    def parse_args():
        parser = argparse.ArgumentParser(description="Web Agent UI")
        parser.add_argument(
            "--ip", type=str, default="127.0.0.1", help="IP地址 (默认: 127.0.0.1)"
        )
        parser.add_argument(
            "--port", type=int, default=7788, help="端口号 (默认: 7788)"
        )
        parser.add_argument(
            "--css-mode", type=str, choices=["basic", "enhanced"], default="enhanced",
            help="CSS样式模式：basic(基础) 或 enhanced(增强) (默认: enhanced)"
        )
        parser.add_argument(
            "--theme", type=str, choices=["Default", "Citrus", "Glass", "Monochrome", "Ocean", "Origin", "Soft"],
            default="Ocean", help="UI主题 (默认: Ocean)"
        )
        return parser.parse_args()

    args = parse_args()
    
    # 使用新的模块化UI构建器创建界面，传入CSS模式和主题参数
    demo = create_ui(
        css_mode=args.css_mode,
        title="Web Agent", 
        subtitle="AI浏览器代理",
        theme_name=args.theme
    )
    
    # 启动Gradio服务器
    demo.launch(server_name=args.ip, server_port=args.port)


if __name__ == "__main__":
    main()
