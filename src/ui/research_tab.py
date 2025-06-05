"""
深度研究标签页组件

提供研究任务输入、查询参数设置和结果展示的UI组件
"""

import gradio as gr
from src.ui.ui_constants import CSS_CLASSES

def create_deep_research_tab():
    """
    创建深度研究标签页
    
    包含研究任务描述、查询参数、执行按钮和结果展示区域
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("🧐 深度研究", id=5):
        with gr.Group(elem_classes=[CSS_CLASSES["CONTROL_PANEL"]]):
            research_task_input = gr.Textbox(
                label="研究任务", 
                lines=5,
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
                interactive=True
            )
            
            with gr.Row():
                max_search_iteration_input = gr.Number(
                    label="最大搜索迭代次数", 
                    value=3,
                    precision=0,
                    interactive=True
                )
                max_query_per_iter_input = gr.Number(
                    label="每次迭代最大查询数", 
                    value=1,
                    precision=0,
                    interactive=True
                )
                
            with gr.Row():
                research_button = gr.Button("▶️ 运行深度研究", variant="primary", scale=2)
                stop_research_button = gr.Button("⏹ 停止", variant="stop", scale=1)
                
        with gr.Group(elem_classes=[CSS_CLASSES["RESULTS_AREA"]]):
            markdown_output_display = gr.Markdown(label="研究报告")
            markdown_download = gr.File(label="下载研究报告")
    
    return (research_task_input, max_search_iteration_input, max_query_per_iter_input,
            research_button, stop_research_button, markdown_output_display, markdown_download)
