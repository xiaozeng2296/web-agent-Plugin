"""
UI常量定义模块

统一管理UI相关常量，包括主题定义、色彩方案、布局配置等
"""

import gradio as gr
from gradio.themes import Citrus, Default, Glass, Monochrome, Ocean, Origin, Soft, Base

# 主题映射表
THEME_MAP = {
    "Default": Default(),
    "Citrus": Citrus(),
    "Glass": Glass(),
    "Monochrome": Monochrome(),
    "Ocean": Ocean(),
    "Origin": Origin(),
    "Soft": Soft(),
}

# 默认主题
DEFAULT_THEME = "Ocean"

# CSS类名常量
CSS_CLASSES = {
    "HEADER": "header-text",
    "THEME_SECTION": "theme-section", 
    "CONTROL_PANEL": "control-panel",
    "RESULTS_AREA": "results-area",
    "BROWSER_VIEW": "browser-view",
    "STATUS_INDICATOR": "status-indicator",
    "FOOTER": "footer-section",
}

# UI布局常量
LAYOUT = {
    "SIDEBAR_WIDTH": "300px",
    "CONTENT_WIDTH": "calc(100% - 320px)",
    "CONTAINER_MAX_WIDTH": "95%",
    "TAB_MIN_HEIGHT": "600px",
    "RESULT_MIN_HEIGHT": "300px",
}

# CSS变量前缀
CSS_VAR_PREFIX = "--webui"

# 基础样式定义 
BASE_CSS = """
:root {
    /* 主要颜色 */
    --webui-primary: #3b82f6;
    --webui-primary-hover: #2563eb;
    --webui-secondary: #6b7280;
    --webui-secondary-hover: #4b5563;
    --webui-accent: #8b5cf6;
    
    /* 背景颜色 */
    --webui-bg-primary: #ffffff;
    --webui-bg-secondary: #f3f4f6;
    --webui-bg-tertiary: #e5e7eb;
    
    /* 文本颜色 */
    --webui-text-primary: #111827;
    --webui-text-secondary: #374151;
    --webui-text-tertiary: #6b7280;
    
    /* 边框颜色 */
    --webui-border: #d1d5db;
    --webui-border-focus: #3b82f6;
    
    /* 成功/错误颜色 */
    --webui-success: #10b981;
    --webui-error: #ef4444;
    --webui-warning: #f59e0b;
    --webui-info: #3b82f6;
    
    /* 间距 */
    --webui-spacing-xs: 4px;
    --webui-spacing-sm: 8px;
    --webui-spacing-md: 16px;
    --webui-spacing-lg: 24px;
    --webui-spacing-xl: 32px;
    
    /* 圆角 */
    --webui-radius-sm: 4px;
    --webui-radius-md: 8px;
    --webui-radius-lg: 12px;
    
    /* 阴影 */
    --webui-shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    --webui-shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    --webui-shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
}

/* 深色模式变量 - 未激活，但已定义供后续使用 */
.dark-mode {
    --webui-primary: #3b82f6;
    --webui-primary-hover: #60a5fa;
    --webui-secondary: #9ca3af;
    --webui-secondary-hover: #d1d5db;
    
    --webui-bg-primary: #111827;
    --webui-bg-secondary: #1f2937;
    --webui-bg-tertiary: #374151;
    
    --webui-text-primary: #f9fafb;
    --webui-text-secondary: #e5e7eb;
    --webui-text-tertiary: #d1d5db;
    
    --webui-border: #4b5563;
    --webui-border-focus: #60a5fa;
}

/* 基础容器样式 */
.gradio-container {
    width: var(--webui-container-width, 95%) !important; 
    max-width: var(--webui-container-max-width, 95%) !important; 
    margin-left: auto !important;
    margin-right: auto !important;
    padding-top: var(--webui-spacing-lg) !important;
}

/* 头部文本样式 */
.header-text {
    text-align: center;
    margin-bottom: var(--webui-spacing-lg);
    padding: var(--webui-spacing-md);
}

.header-text h1 {
    margin-bottom: var(--webui-spacing-xs);
    color: var(--webui-primary);
    font-size: 2.5rem;
}

.header-text h3 {
    color: var(--webui-text-secondary);
    font-weight: normal;
    font-size: 1.25rem;
}

/* 主题区域样式 */
.theme-section {
    margin-bottom: var(--webui-spacing-md);
    padding: var(--webui-spacing-md);
    border-radius: var(--webui-radius-md);
    background-color: var(--webui-bg-secondary);
    border: 1px solid var(--webui-border);
    box-shadow: var(--webui-shadow-sm);
}

/* 控制面板样式 */
.control-panel {
    padding: var(--webui-spacing-md);
    background-color: var(--webui-bg-secondary);
    border-radius: var(--webui-radius-md);
    margin-bottom: var(--webui-spacing-md);
}

/* 结果区域样式 */
.results-area {
    padding: var(--webui-spacing-md);
    background-color: var(--webui-bg-secondary);
    border-radius: var(--webui-radius-md);
    margin-top: var(--webui-spacing-md);
}

/* 浏览器视图样式 */
.browser-view {
    border: 1px solid var(--webui-border);
    border-radius: var(--webui-radius-md);
    overflow: hidden;
    background-color: var(--webui-bg-tertiary);
    min-height: 400px;
    margin: var(--webui-spacing-md) 0;
}

/* 状态指示器样式 */
.status-indicator {
    display: inline-flex;
    align-items: center;
    padding: var(--webui-spacing-xs) var(--webui-spacing-md);
    border-radius: var(--webui-radius-sm);
    font-size: 0.875rem;
    font-weight: 500;
    margin-right: var(--webui-spacing-md);
}

.status-indicator.active {
    background-color: var(--webui-success);
    color: white;
}

.status-indicator.inactive {
    background-color: var(--webui-secondary);
    color: white;
}

.status-indicator.error {
    background-color: var(--webui-error);
    color: white;
}

/* 底部区域样式 */
.footer-section {
    margin-top: var(--webui-spacing-xl);
    padding: var(--webui-spacing-md);
    text-align: center;
    color: var(--webui-text-tertiary);
    font-size: 0.875rem;
}

/* 响应式调整 */
@media (max-width: 1024px) {
    .gradio-container {
        width: 98% !important;
        max-width: 98% !important;
    }
}

@media (max-width: 768px) {
    .gradio-container {
        width: 100% !important;
        max-width: 100% !important;
        padding: var(--webui-spacing-sm) !important;
    }
    
    .header-text h1 {
        font-size: 2rem;
    }
    
    .header-text h3 {
        font-size: 1rem;
    }
}
"""
