# -*- coding: utf-8 -*-
# @Time : 2025/6/4 16:24
import os
import time
from src.utils.pptai_api import *


def get_ppt(content):
    """
    根据markdown内容生成PPT并返回文件路径
    
    Args:
        content: markdown格式的内容文本
        
    Returns:
        str: 生成的PPT文件路径
    """
    api_key = 'ak_6_wW3ET6FpFr5LJCWz'
    uid = 'test'
    api_token = create_api_token(api_key, uid, None)
    data_url = parse_file_data(api_token, file_path=None, file_url=None, content=content)
    
    # 生成大纲
    print('\n\n========== 正在生成大纲 ===========')
    outline = generate_outline(api_token, '', data_url, None)

    # 生成大纲内容同时异步生成PPT
    print('\n\n========== 正在异步生成大纲内容 ===========')
    pptInfo = async_generate_content(api_token, outline, data_url, None, None)

    ppt_id = pptInfo['id']
    print(f"pptId: {ppt_id}")

    # 下载PPT
    print('\n\n========== 正在下载PPT ===========')
    count = 0
    while count < 30:
        # 等待PPT文件可下载
        pptInfo = download_pptx(api_token, ppt_id)
        if pptInfo and 'fileUrl' in pptInfo and pptInfo['fileUrl']:
            break
        count = count + 1
        time.sleep(1)
    
    url = pptInfo['fileUrl']
    # 使用当前时间戳生成唯一文件名
    timestamp = int(time.time())
    # 创建保存路径（相对于当前工作目录）
    save_dir = os.path.join(os.getcwd(), 'tmp', 'ppt')
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, f'report_{timestamp}_{ppt_id}.pptx')
    
    print(f'PPT链接: {url}')
    download(url, save_path)
    print('PPT下载完成，保存路径：' + save_path)
    
    # 返回文件路径，供webui使用
    return save_path

if __name__ == '__main__':
    # 根据主题异步流式生成PPT

    # 官网 https://docmee.cn
    # 开放平台 https://docmee.cn/open-platform/api

    # 填写你的API-KEY
    api_key = 'ak_6_wW3ET6FpFr5LJCWz'

    # 第三方用户ID（数据隔离）
    uid = 'test'
    subject = 'AI未来的发展'

    # 创建 api token (有效期2小时，建议缓存到redis，同一个 uid 创建时之前的 token 会在10秒内失效)
    api_token = create_api_token(api_key, uid, None)
    print(f'apiToken: {api_token}')

    content = """
    带货短视频创作者移动端剪辑APP对比报告
随着短视频平台的兴起，带货短视频创作者对高效、便捷的视频编辑工具需求日益增长。本报告将对比市面上五款主流的移动端剪辑APP，分析它们的优缺点，帮助您选择最适合您的工具。

1. 剪映
优点：

操作简单，易于上手。
分享方便，可以直接发布到各大平台。
提供丰富的视频模板和素材。
缺点：

专业性不足，对于高级用户可能不够用。
部分功能需要付费解锁。
导出时间较长且存在水印问题。
2. 万兴喵影
优点：

支持多平台使用，用户可以在不同设备间无缝切换。
功能免费，无需额外付费。
素材丰富，满足多样化创作需求。
缺点：

学习成本较高，初学者可能需要一段时间适应。
部分素材较为陈旧，更新速度较快。
存在水印问题。
3. 必剪
优点：

提供高清录屏功能，适合高质量视频制作。
可以直接导出并在B站发布，方便快捷。
缺点：

导出质量可能受影响。
存在一些功能上的bug，影响用户体验。
4. 快影
优点：

官方指定的视频编辑软件，提供分割、修剪、拼接、倒放、滤镜、音乐等功能。
操作难度适中，适合大多数用户。
可以直接导出并在快手发布。
缺点：

导出质量可能受影响。
仅适用于手机端，不支持其他平台。
5. Inshot
优点：

操作简单，易于上手。
素材丰富，满足多样化创作需求。
缺点：

专业性不足，对于高级用户可能不够用。
部分功能需要付费解锁。
结论
综合以上五款剪辑APP的优缺点，我们可以得出以下结论：

剪映 和 Inshot 适合初学者，操作简单且素材丰富，但部分功能需要付费。
万兴喵影 支持多平台使用，功能免费，但学习成本较高。
必剪 提供高清录屏功能，适合高质量视频制作，但存在一些功能上的bug。
快影 是官方指定的视频编辑软件，操作难度适中，但仅适用于手机端。
根据您的具体需求，您可以选择最适合您的剪辑APP。希望本报告能为您提供有价值的参考。
    """

    data_url = parse_file_data(api_token,file_path=None,file_url=None,content=content)
    # 生成大纲
    print('\n\n========== 正在生成大纲 ==========')
    outline = generate_outline(api_token, '', data_url, None)

    # 生成大纲内容同时异步生成PPT
    print('\n\n========== 正在异步生成大纲内容 ==========')
    pptInfo = async_generate_content(api_token, outline, data_url, None, None)

    ppt_id = pptInfo['id']
    print(f"pptId: {ppt_id}")

    # 下载PPT
    print('\n\n========== 正在下载PPT ==========')
    count = 0
    while count < 30:
        # 等待PPT文件可下载
        pptInfo = download_pptx(api_token, ppt_id)
        if pptInfo and 'fileUrl' in pptInfo and pptInfo['fileUrl']:
            break
        count = count + 1
        time.sleep(1)
    url = pptInfo['fileUrl']
    save_path = os.getcwd() + f'/{ppt_id}.pptx'
    print(f'ppt链接: {url}')
    download(url, save_path)
    print('ppt下载完成，保存路径：' + save_path)