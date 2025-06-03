#!/usr/bin/env python
# -*- coding: utf-8 -*-

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse

import requests
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DingTalkSender:
    """
    钉钉消息发送工具类
    """
    def __init__(self, webhook_url, secret=None):
        """
        初始化钉钉发送器
        
        参数:
            webhook_url: 钉钉机器人的Webhook URL
            secret: 安全设置的秘钥，如果机器人安全设置为"加签"则需要提供
        """
        self.webhook_url = webhook_url
        self.secret = secret

    def _get_signed_url(self):
        """
        根据密钥生成签名URL
        
        返回:
            签名后的URL
        """
        if not self.secret:
            return self.webhook_url
            
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode(), 
            string_to_sign.encode(), 
            digestmod=hashlib.sha256
        ).digest()
        
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
        return url

    def send_text(self, content, at_mobiles=None, at_all=False, max_retries=3):
        """
        发送文本消息
        
        参数:
            content: 消息内容
            at_mobiles: 需要@的人的手机号列表
            at_all: 是否@所有人
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        if not at_mobiles:
            at_mobiles = []
            
        data = {
            "msgtype": "text",
            "text": {"content": content},
            "at": {
                "atMobiles": at_mobiles,
                "isAtAll": at_all
            }
        }
        
        return self._send_request(data, max_retries)
        
    def send_markdown(self, title, text, at_mobiles=None, at_all=False, max_retries=3):
        """
        发送Markdown消息
        
        参数:
            title: 标题
            text: Markdown格式的消息内容
            at_mobiles: 需要@的人的手机号列表
            at_all: 是否@所有人
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        if not at_mobiles:
            at_mobiles = []
            
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            },
            "at": {
                "atMobiles": at_mobiles,
                "isAtAll": at_all
            }
        }
        
        return self._send_request(data, max_retries)
    
    def send_file_content(self, file_path, at_mobiles=None, at_all=False, max_retries=3):
        """
        发送文件内容作为Markdown消息
        
        参数:
            file_path: 文件路径
            at_mobiles: 需要@的人的手机号列表
            at_all: 是否@所有人
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
                
            title = f"研究报告 - {os.path.basename(file_path)}"
            
            # 如果内容过长，进行截断并添加提示
            max_length = 5000  # 钉钉Markdown消息有长度限制
            if len(file_content) > max_length:
                file_content = file_content[:max_length] + "\n\n...\n\n(内容过长，已截断，请查看完整文件)"
                
            # 添加消息头部信息
            header = f"### 研究报告: {os.path.basename(file_path)}\n\n"
            header += f"**时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            header += f"**文件大小**: {os.path.getsize(file_path) / 1024:.2f} KB\n\n"
            header += "---\n\n"
            
            # 组合完整消息内容
            markdown_content = header + file_content
            
            return self.send_markdown(title, markdown_content, at_mobiles, at_all, max_retries)
            
        except Exception as e:
            logger.error(f"读取或发送文件内容失败: {e}")
            return False

    def _send_request(self, data, max_retries=3):
        """
        发送HTTP请求到钉钉
        
        参数:
            data: 要发送的数据
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        url = self._get_signed_url()
        
        retry_count = 0
        while retry_count < max_retries:
            try:
                response = requests.post(url, headers=headers, data=json.dumps(data))
                result = response.json()
                
                if result.get('errcode') == 0:
                    logger.info("消息发送成功")
                    return True
                else:
                    error_msg = result.get('errmsg', '未知错误')
                    logger.error(f"发送消息失败: {error_msg}")
                    retry_count += 1
                    time.sleep(2)  # 等待2秒后重试
                    
            except Exception as e:
                logger.error(f"请求发送失败 (尝试 {retry_count + 1}/{max_retries}): {e}")
                retry_count += 1
                time.sleep(2)
        
        logger.error(f"发送消息失败，已达到最大重试次数: {max_retries}")
        return False


def send_report_to_dingtalk(file_path, webhook_url, secret=None, at_mobiles=None, at_all=False):
    """
    发送研究报告到钉钉
    
    参数:
        file_path: 报告文件路径
        webhook_url: 钉钉机器人的Webhook URL
        secret: 安全设置的秘钥
        at_mobiles: 需要@的人的手机号列表
        at_all: 是否@所有人
        
    返回:
        成功返回True，失败返回False
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        logger.error(f"报告文件不存在: {file_path}")
        return False
    
    # 创建钉钉发送器
    sender = DingTalkSender(webhook_url, secret)
    
    # 发送文件内容
    result = sender.send_file_content(file_path, at_mobiles, at_all)
    
    return result


if __name__ == "__main__":
    # 加载.env文件中的配置
    # 首先获取项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(current_dir, '.env')
    
    # 加载.env文件
    load_dotenv(env_path)
    
    # 报告文件路径
    report_file = "/Users/cds-dn-175/PycharmProjects/MyScript/web-agent-Plugin/tmp/deep_research/0c194f4b-f257-49dd-ae42-2e36506d7507/final_report.md"
    
    # 从环境变量中获取钉钉机器人配置
    webhook_url = os.getenv('webhook_url')
    secret = os.getenv('secret')
    
    if not webhook_url or not secret:
        logger.error("钉钉配置信息不完整，请检查.env文件")
        exit(1)
    
    logger.info("已从.env文件加载钉钉配置")
    
    # 要@的人的手机号列表
    at_mobiles = []  # 例如 ["13812345678", "13987654321"]
    
    # 是否@所有人
    at_all = False
    
    logger.info(f"开始发送报告到钉钉: {os.path.basename(report_file)}")
    success = send_report_to_dingtalk(report_file, webhook_url, secret, at_mobiles, at_all)
    
    if success:
        logger.info("报告发送成功！")
    else:
        logger.error("报告发送失败！")
