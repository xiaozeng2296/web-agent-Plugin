"""
语言模型设置标签页组件

提供LLM提供商、模型名称、参数等设置的UI组件
"""

import gradio as gr
from src.ui.ui_constants import CSS_CLASSES
from src.utils.utils import model_names

def create_llm_settings_tab():
    """
    创建语言模型设置标签页
    
    包含LLM提供商、模型名称、上下文长度、温度等设置选项
    
    返回:
        tuple: 包含所有创建的组件
    """
    with gr.TabItem("🔧 模型设置", id=2):
        with gr.Group(elem_classes=[CSS_CLASSES["THEME_SECTION"]]):
            llm_provider = gr.Dropdown(
                choices=[provider for provider, model in model_names.items()],
                label="LLM提供商",
                value="alibaba",
                info="选择您偏好的语言模型提供商",
                interactive=True
            )
            llm_model_name = gr.Dropdown(
                label="模型名称",
                choices=model_names['alibaba'],
                value="qwen-max",
                interactive=True,
                allow_custom_value=True,
                info="选择下拉选项中的模型或直接输入自定义模型名称"
            )
            ollama_num_ctx = gr.Slider(
                minimum=2 ** 8,
                maximum=2 ** 16,
                value=16000,
                step=1,
                label="Ollama上下文长度",
                info="控制模型需要处理的最大上下文长度（越小越快）",
                visible=False,
                interactive=True
            )
            llm_temperature = gr.Slider(
                minimum=0.0,
                maximum=2.0,
                value=0.2,
                step=0.1,
                label="温度",
                info="控制模型输出的随机性",
                interactive=True
            )
            with gr.Row():
                llm_base_url = gr.Textbox(
                    label="基础URL",
                    value="",
                    info="API端点URL（如果需要）"
                )
                llm_api_key = gr.Textbox(
                    label="API密钥",
                    type="password",
                    value="",
                    info="您的API密钥（留空使用.env中的配置）"
                )
                
    # 绑定提供商变更事件，更新上下文长度滑块可见性
    def update_llm_num_ctx_visibility(provider):
        """更新上下文长度滑块可见性"""
        return gr.update(visible=provider == "ollama")
        
    llm_provider.change(
        fn=update_llm_num_ctx_visibility,
        inputs=llm_provider,
        outputs=ollama_num_ctx
    )
                
    return llm_provider, llm_model_name, ollama_num_ctx, llm_temperature, llm_base_url, llm_api_key
