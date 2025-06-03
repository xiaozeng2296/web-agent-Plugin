#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
钉钉机器人消息发送工具类

提供了向钉钉群组发送各种消息的功能，包括：
- 文本消息
- Markdown格式消息
- 文件内容消息

"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import requests
from dotenv import load_dotenv

# 获取logger
logger = logging.getLogger(__name__)


class DingTalkRobot:
    """
    钉钉机器人消息发送工具类
    """
    # 配置缓存
    _config_cache = None
    _env_loaded = False
    
    @classmethod
    def _load_config_from_env(cls) -> Dict[str, str]:
        """
        从环境变量中加载配置
        
        返回:
            配置字典，包含webhook_url和secret
        """
        if cls._config_cache is not None:
            return cls._config_cache
            
        # 获取项目根目录
        proj_root = Path(__file__).parent.parent.parent
        env_path = proj_root / '.env'
        
        # 加载.env文件
        load_dotenv(env_path)
        
        # 从环境变量中获取配置
        webhook_url = os.getenv('webhook_url')
        secret = os.getenv('secret')
        
        if not webhook_url or not secret:
            error_msg = "钉钉配置信息不完整，请检查.env文件"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        # 缓存配置
        cls._config_cache = {
            "webhook_url": webhook_url,
            "secret": secret
        }
        
        cls._env_loaded = True
        logger.debug("已从.env文件加载钉钉配置")
        
        return cls._config_cache
    
    @classmethod
    def _get_signed_url(cls, webhook_url: str, secret: str) -> str:
        """
        根据密钥生成签名URL
        
        参数:
            webhook_url: 钉钉webhook URL
            secret: 密钥
            
        返回:
            签名后的URL
        """
        # 生成时间戳，毫秒
        timestamp = str(round(time.time() * 1000))
        
        # 构建签名字符串
        string_to_sign = f"{timestamp}\n{secret}"
        
        # 使用HMAC-SHA256计算签名
        hmac_code = hmac.new(
            secret.encode(), 
            string_to_sign.encode(), 
            digestmod=hashlib.sha256
        ).digest()
        
        # Base64编码并URL编码
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        
        # 构建完整URL
        signed_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"
        return signed_url
    
    @classmethod
    def _send_request(cls, 
                      data: Dict, 
                      webhook_url: str, 
                      secret: str, 
                      max_retries: int = 3) -> bool:
        """
        发送HTTP请求到钉钉
        
        参数:
            data: 要发送的数据
            webhook_url: 钉钉webhook URL
            secret: 密钥
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        url = cls._get_signed_url(webhook_url, secret)
        
        retry_count = 0
        while retry_count < max_retries:
            try:
                # 记录请求开始时间
                start_time = time.time()
                
                response = requests.post(url, headers=headers, data=json.dumps(data), timeout=5)
                result = response.json()
                
                # 记录请求耗时
                elapsed_time = time.time() - start_time
                logger.debug(f"钉钉API请求耗时: {elapsed_time:.2f}秒")
                
                if result.get('errcode') == 0:
                    logger.info("消息发送成功")
                    return True
                else:
                    error_msg = result.get('errmsg', '未知错误')
                    logger.error(f"发送消息失败: {error_msg}")
                    retry_count += 1
                    time.sleep(2)  # 等待2秒后重试
                    
            except requests.exceptions.Timeout:
                logger.error(f"请求超时 (尝试 {retry_count + 1}/{max_retries})")
                retry_count += 1
                time.sleep(2)
            except requests.exceptions.ConnectionError:
                logger.error(f"连接错误 (尝试 {retry_count + 1}/{max_retries})")
                retry_count += 1
                time.sleep(3)  # 连接错误等待时间更长
            except Exception as e:
                logger.error(f"请求发送失败 (尝试 {retry_count + 1}/{max_retries}): {e}")
                retry_count += 1
                time.sleep(2)
        
        logger.error(f"发送消息失败，已达到最大重试次数: {max_retries}")
        return False
    
    @classmethod
    def send_text(cls, 
                  content: str, 
                  at_mobiles: Optional[List[str]] = None, 
                  at_all: bool = False, 
                  webhook_url: Optional[str] = None, 
                  secret: Optional[str] = None, 
                  max_retries: int = 3) -> bool:
        """
        发送文本消息
        
        参数:
            content: 消息内容
            at_mobiles: 需要@的人的手机号列表
            at_all: 是否@所有人
            webhook_url: 可选，钉钉webhook URL，如不提供则从环境变量获取
            secret: 可选，密钥，如不提供则从环境变量获取
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        # 如果没有提供webhook_url和secret，从环境变量加载
        if webhook_url is None or secret is None:
            config = cls._load_config_from_env()
            webhook_url = webhook_url or config["webhook_url"]
            secret = secret or config["secret"]
        
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
        
        return cls._send_request(data, webhook_url, secret, max_retries)
    
    @classmethod
    def send_markdown(cls, 
                      title: str, 
                      text: str, 
                      at_mobiles: Optional[List[str]] = None, 
                      at_all: bool = False, 
                      webhook_url: Optional[str] = None, 
                      secret: Optional[str] = None, 
                      max_retries: int = 3) -> bool:
        """
        发送Markdown消息
        
        参数:
            title: 标题
            text: Markdown格式的消息内容
            at_mobiles: 需要@的人的手机号列表
            at_all: 是否@所有人
            webhook_url: 可选，钉钉webhook URL，如不提供则从环境变量获取
            secret: 可选，密钥，如不提供则从环境变量获取
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        # 如果没有提供webhook_url和secret，从环境变量加载
        if webhook_url is None or secret is None:
            config = cls._load_config_from_env()
            webhook_url = webhook_url or config["webhook_url"]
            secret = secret or config["secret"]
            
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
        
        return cls._send_request(data, webhook_url, secret, max_retries)
    
    @classmethod
    def send_link(cls, 
                  title: str, 
                  text: str, 
                  message_url: str, 
                  pic_url: Optional[str] = None, 
                  webhook_url: Optional[str] = None, 
                  secret: Optional[str] = None, 
                  max_retries: int = 3) -> bool:
        """
        发送链接消息
        
        参数:
            title: 标题
            text: 消息内容
            message_url: 点击消息跳转的URL
            pic_url: 图片URL
            webhook_url: 可选，钉钉webhook URL，如不提供则从环境变量获取
            secret: 可选，密钥，如不提供则从环境变量获取
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        # 如果没有提供webhook_url和secret，从环境变量加载
        if webhook_url is None or secret is None:
            config = cls._load_config_from_env()
            webhook_url = webhook_url or config["webhook_url"]
            secret = secret or config["secret"]
            
        data = {
            "msgtype": "link",
            "link": {
                "title": title,
                "text": text,
                "picUrl": pic_url,
                "messageUrl": message_url
            }
        }
        
        return cls._send_request(data, webhook_url, secret, max_retries)
    
    @classmethod
    def send_file_content(cls, 
                          file_path: str, 
                          at_mobiles: Optional[List[str]] = None, 
                          at_all: bool = False, 
                          webhook_url: Optional[str] = None, 
                          secret: Optional[str] = None, 
                          max_retries: int = 3) -> bool:
        """
        发送文件内容作为Markdown消息
        
        参数:
            file_path: 文件路径
            at_mobiles: 需要@的人的手机号列表
            at_all: 是否@所有人
            webhook_url: 可选，钉钉webhook URL，如不提供则从环境变量获取
            secret: 可选，密钥，如不提供则从环境变量获取
            max_retries: 最大重试次数
        
        返回:
            成功返回True，失败返回False
        """
        # 如果没有提供webhook_url和secret，从环境变量加载
        if webhook_url is None or secret is None:
            config = cls._load_config_from_env()
            webhook_url = webhook_url or config["webhook_url"]
            secret = secret or config["secret"]
            
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return False
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
                
            file_name = os.path.basename(file_path)
            file_size_kb = os.path.getsize(file_path) / 1024
            file_ext = os.path.splitext(file_path)[1].lower()
            
            title = f"文件分享 - {file_name}"
            
            # 如果内容过长，进行截断并添加提示
            max_length = 5000  # 钉钉Markdown消息有长度限制
            if len(file_content) > max_length:
                truncated_content = file_content[:max_length]
                file_content = truncated_content + "\n\n...\n\n(内容过长，已截断，请查看完整文件)"
            
            # 添加消息头部信息
            header = f"### 文件名: {file_name}\n\n"
            header += f"**时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            header += f"**文件大小**: {file_size_kb:.2f} KB\n\n"
            header += "---\n\n"
            
            # 组合完整消息内容
            if file_ext in [".md", ".txt"]:
                # 对于Markdown和文本文件，保留原格式
                markdown_content = header + file_content
            else:
                # 对于其他类型的文件，可能需要不同的处理方式
                markdown_content = header + "```\n" + file_content + "\n```"
            
            return cls.send_markdown(title, markdown_content, at_mobiles, at_all, webhook_url, secret, max_retries)
            
        except UnicodeDecodeError:
            logger.error(f"文件编码不是UTF-8，无法作为文本发送: {file_path}")
            return False
        except Exception as e:
            logger.error(f"读取或发送文件内容失败: {e}")
            return False
    
    @classmethod
    def send_report(cls, 
                    file_path: str, 
                    at_mobiles: Optional[List[str]] = None, 
                    at_all: bool = False) -> bool:
        """
        发送研究报告到钉钉
        
        参数:
            file_path: 报告文件路径
            at_mobiles: 需要@的人的手机号列表 (可选)
            at_all: 是否@所有人 (可选)
            
        返回:
            成功返回True，失败返回False
        """
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"报告文件不存在: {file_path}")
            return False
        
        try:
            # 记录文件信息
            file_size_kb = os.path.getsize(file_path) / 1024
            logger.info(f"准备发送报告: {os.path.basename(file_path)}，大小: {file_size_kb:.2f} KB")
            
            # 发送文件内容
            start_time = time.time()
            result = cls.send_file_content(file_path, at_mobiles, at_all)
            elapsed_time = time.time() - start_time
            
            if result:
                logger.info(f"报告发送成功，耗时: {elapsed_time:.2f}秒")
            else:
                logger.error(f"报告发送失败，耗时: {elapsed_time:.2f}秒")
                
            return result
            
        except Exception as e:
            logger.error(f"发送报告过程中发生错误: {e}")
            return False
