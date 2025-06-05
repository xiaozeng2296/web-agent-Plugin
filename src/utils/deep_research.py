import pdb

from dotenv import load_dotenv

load_dotenv()
import asyncio
import os
import sys
import logging
from pprint import pprint
from uuid import uuid4
from src.utils import utils
from src.agent.custom_agent import CustomAgent
import json
import re
from browser_use.agent.service import Agent
from browser_use.browser.browser import BrowserConfig, Browser
from browser_use.agent.views import ActionResult
from browser_use.browser.context import BrowserContext
from browser_use.controller.service import Controller, DoneAction
from main_content_extractor import MainContentExtractor
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    SystemMessage
)
from json_repair import repair_json
from src.agent.custom_prompts import CustomSystemPrompt, CustomAgentMessagePrompt
from src.controller.custom_controller import CustomController
from src.browser.custom_browser import CustomBrowser
from src.browser.custom_context import BrowserContextConfig, BrowserContext
from browser_use.browser.context import (
    BrowserContextConfig,
    BrowserContextWindowSize,
)

logger = logging.getLogger(__name__)


async def deep_research(task, llm, agent_state=None, **kwargs):
    task_id = str(uuid4())
    save_dir = kwargs.get("save_dir", os.path.join(f"./tmp/deep_research/{task_id}"))
    logger.info(f"Save Deep Research at: {save_dir}")
    os.makedirs(save_dir, exist_ok=True)

    # max qyery num per iteration
    max_query_num = kwargs.get("max_query_num", 3)

    use_own_browser = kwargs.get("use_own_browser", False)
    extra_chromium_args = []

    if use_own_browser:
        cdp_url = os.getenv("CHROME_CDP", kwargs.get("chrome_cdp", None))
        # TODO: if use own browser, max query num must be 1 per iter, how to solve it?
        max_query_num = 1
        chrome_path = os.getenv("CHROME_PATH", None)
        if chrome_path == "":
            chrome_path = None
        chrome_user_data = os.getenv("CHROME_USER_DATA", None)
        if chrome_user_data:
            extra_chromium_args += [f"--user-data-dir={chrome_user_data}"]

        browser = CustomBrowser(
            config=BrowserConfig(
                headless=kwargs.get("headless", False),
                cdp_url=cdp_url,
                disable_security=kwargs.get("disable_security", True),
                chrome_instance_path=chrome_path,
                extra_chromium_args=extra_chromium_args,
            )
        )
        browser_context = await browser.new_context()
    else:
        browser = None
        browser_context = None

    controller = CustomController()

    @controller.registry.action(
        'Extract page content to get the pure markdown.',
    )
    async def extract_content(browser: BrowserContext):
        page = await browser.get_current_page()
        # use jina reader
        # url = page.url
        #
        # jina_url = f"https://r.jina.ai/{url}"
        # await page.goto(jina_url)
        output_format = 'markdown'
        content = MainContentExtractor.extract(  # type: ignore
            html=await page.content(),
            output_format=output_format,
        )
        msg = f'Extracted page content:\n{content}\n'
        logger.info(msg)
        return ActionResult(extracted_content=msg)

    search_system_prompt = f"""
你是一个**对比分析专家**，一个专门通过具有**自动执行能力**的网络浏览器进行深入研究和对比分析的AI助手。你的专长在于系统性地收集和分析不同事物、产品、概念或方法的信息，并提供有深度的对比洞察。你将分析用户指令，设计详细的对比分析方案，并确定收集所需信息的必要搜索查询。

**你的任务：**

根据用户指定的对比主题，你将：

1. **制定对比分析计划：** 概述需要调查的对象、特点、关键对比维度等方面。该计划应涵盖全面的对比分析框架。
2. **生成搜索查询：** 基于你的分析计划，生成一系列特定的搜索查询，以便在网络浏览器中执行。这些查询应旨在高效收集不同对象的信息、特点、评价、数据等关键信息。

**输出格式：**

你的输出将是具有以下结构的JSON对象：

```json
{{
"plan": "简明扼要的对比分析计划，概述需要调查的对象和关键分析维度。",
"queries": [
"对比搜索查询1",
"对比搜索查询2",
//... 最多 {max_query_num} 个搜索查询
]
}}

**重要提示：**

* 限制输出最多 **{max_query_num}** 个搜索查询。
* 设计搜索查询以收集全面且具体的信息。考虑使用产品名称、功能关键词、评测关键词等。
* 确保搜索查询涵盖多个竞争对手和多个分析维度。
* 如果你已收集到所有需要的信息且不需要进一步的搜索查询，请输出空查询列表：`[]`
* 确保输出的搜索查询与历史查询不同。

**输入：**

1. **用户指令：** 用户给出的原始指令，包含待分析的产品或服务信息。
2. **以往查询：** 历史查询记录。
3. **以往搜索结果：** 从之前的搜索查询中收集的文本数据。如果没有以往的搜索结果，此字符串将为空。
"""
    search_messages = [SystemMessage(content=search_system_prompt)]

    record_system_prompt = """
        你是一名专业信息记录员。你的职责是处理用户指令、当前搜索结果和先前记录的信息，以提取、总结并记录有助于满足用户需求的新的、有用的信息。你的输出将是一个JSON格式的列表，其中每个元素代表一条提取的信息，并遵循以下结构：`{"url": "来源网址", "title": "来源标题", "summary_content": "简明摘要", "thinking": "分析推理"}`。

    **重要考虑事项：**

    1. **最小化信息损失：** 在保持简洁的同时，优先保留来源中的重要细节和细微差别。力求创建能够捕捉信息精髓而不过度简化的摘要。**关键是，务必在`summary_content`中保留关键数据和数字。这对于后续阶段（如生成表格和报告）至关重要。**

    2. **避免冗余：** 不要记录已经存在于先前记录信息中的内容。检查语义相似性，而非仅仅是完全匹配。然而，如果相同信息在新来源中以不同方式表达，且这种变化增加了有价值的上下文或清晰度，则应将其包括在内。

    3. **来源信息：** 为每条总结的信息提取并包含来源标题和URL。这对于验证和背景信息至关重要。**当前搜索结果以特定格式提供，每个项目以"Title:"开头，后跟标题，然后是"URL Source:"，后跟URL，最后是"Markdown Content:"，后跟内容。请从这个结构中提取标题和URL。** 如果某条信息无法归因于提供的搜索结果中的特定来源，请使用`"url": "unknown"`和`"title": "unknown"`。

    4. **思考与报告结构：** 为每条提取的信息添加一个`"thinking"`键。此字段应包含你对该信息如何在报告中使用的评估，它可能属于哪个部分（如引言、背景、分析、结论、特定子主题），以及关于其重要性或与其他信息的联系的任何其他相关思考。

    **输出格式：**

    提供JSON格式的列表作为你的输出。列表中的每个项目必须遵循以下格式：

    ```json
    [
      {
        "url": "来源网址_1",
        "title": "来源标题_1",
        "summary_content": "内容的简明摘要。记住在此处包含关键数据和数字。",
        "thinking": "这可用于引言部分来设定背景。它也与该主题历史部分有关。"
      },
      // ... 更多条目
      {
        "url": "unknown",
        "title": "unknown",
        "summary_content": "没有明确来源的内容的简明摘要",
        "thinking": "这可能是有用的背景信息，但我需要验证其准确性。可用于方法部分来解释数据如何收集。"
      }
    ]
    ```

    **输入：**

    1. **用户指令：** 用户给出的原始指令。这帮助你确定什么类型的信息将是有用的，以及如何构建你的思考。
    2. **先前记录的信息：** 从先前的搜索和处理中收集并记录的文本数据，表示为单个文本字符串。
    3. **当前搜索计划：** 当前搜索的研究计划。
    4. **当前搜索查询：** 当前的搜索查询。
    5. **当前搜索结果：** 从最近的搜索查询中收集的文本数据。
        """
    record_messages = [SystemMessage(content=record_system_prompt)]

    search_iteration = 0
    max_search_iterations = kwargs.get("max_search_iterations", 10)  # Limit search iterations to prevent infinite loop
    use_vision = kwargs.get("use_vision", False)

    history_query = []
    history_infos = []
    try:
        while search_iteration < max_search_iterations:
            search_iteration += 1
            logger.info(f"Start {search_iteration}th Search...")
            history_query_ = json.dumps(history_query, indent=4)
            history_infos_ = json.dumps(history_infos, indent=4)
            query_prompt = f"This is search {search_iteration} of {max_search_iterations} maximum searches allowed.\n User Instruction:{task} \n Previous Queries:\n {history_query_} \n Previous Search Results:\n {history_infos_}\n"
            search_messages.append(HumanMessage(content=query_prompt))
            ai_query_msg = llm.invoke(search_messages[:1] + search_messages[1:][-1:])
            search_messages.append(ai_query_msg)
            if hasattr(ai_query_msg, "reasoning_content"):
                logger.info("🤯 Start Search Deep Thinking: ")
                logger.info(ai_query_msg.reasoning_content)
                logger.info("🤯 End Search Deep Thinking")
            ai_query_content = ai_query_msg.content.replace("```json", "").replace("```", "")
            ai_query_content = repair_json(ai_query_content)
            ai_query_content = json.loads(ai_query_content)
            query_plan = ai_query_content["plan"]
            logger.info(f"Current Iteration {search_iteration} Planing:")
            logger.info(query_plan)
            query_tasks = ai_query_content["queries"]
            if not query_tasks:
                break
            else:
                query_tasks = query_tasks[:max_query_num]
                history_query.extend(query_tasks)
                logger.info("Query tasks:")
                logger.info(query_tasks)

            # 2. Perform Web Search and Auto exec
            # Parallel BU agents
            add_infos = "1. Please click on the most relevant link to get information and go deeper, instead of just staying on the search page. \n" \
                        "2. When opening a PDF file, please remember to extract the content using extract_content instead of simply opening it for the user to view.\n"
            if use_own_browser:
                agent = CustomAgent(
                    task=query_tasks[0],
                    llm=llm,
                    add_infos=add_infos,
                    browser=browser,
                    browser_context=browser_context,
                    use_vision=use_vision,
                    system_prompt_class=CustomSystemPrompt,
                    agent_prompt_class=CustomAgentMessagePrompt,
                    max_actions_per_step=5,
                    controller=controller
                )
                agent_result = await agent.run(max_steps=kwargs.get("max_steps", 10))
                query_results = [agent_result]
                # Manually close all tab
                session = await browser_context.get_session()
                pages = session.context.pages
                await browser_context.create_new_tab()
                for page_id, page in enumerate(pages):
                    await page.close()

            else:
                agents = [CustomAgent(
                    task=task,
                    llm=llm,
                    add_infos=add_infos,
                    browser=browser,
                    browser_context=browser_context,
                    use_vision=use_vision,
                    system_prompt_class=CustomSystemPrompt,
                    agent_prompt_class=CustomAgentMessagePrompt,
                    max_actions_per_step=5,
                    controller=controller,
                ) for task in query_tasks]
                query_results = await asyncio.gather(
                    *[agent.run(max_steps=kwargs.get("max_steps", 10)) for agent in agents])

            if agent_state and agent_state.is_stop_requested():
                # Stop
                break
            # 3. Summarize Search Result
            query_result_dir = os.path.join(save_dir, "query_results")
            os.makedirs(query_result_dir, exist_ok=True)
            for i in range(len(query_tasks)):
                query_result = query_results[i].final_result()
                if not query_result:
                    continue
                querr_save_path = os.path.join(query_result_dir, f"{search_iteration}-{i}.md")
                logger.info(f"save query: {query_tasks[i]} at {querr_save_path}")
                with open(querr_save_path, "w", encoding="utf-8") as fw:
                    fw.write(f"Query: {query_tasks[i]}\n")
                    fw.write(query_result)
                # split query result in case the content is too long
                query_results_split = query_result.split("Extracted page content:")
                for qi, query_result_ in enumerate(query_results_split):
                    if not query_result_:
                        continue
                    else:
                        # TODO: limit content lenght: 128k tokens, ~3 chars per token
                        query_result_ = query_result_[:128000 * 3]
                    history_infos_ = json.dumps(history_infos, indent=4)
                    record_prompt = f"User Instruction:{task}. \nPrevious Recorded Information:\n {history_infos_}\n Current Search Iteration: {search_iteration}\n Current Search Plan:\n{query_plan}\n Current Search Query:\n {query_tasks[i]}\n Current Search Results: {query_result_}\n "
                    record_messages.append(HumanMessage(content=record_prompt))
                    ai_record_msg = llm.invoke(record_messages[:1] + record_messages[-1:])
                    record_messages.append(ai_record_msg)
                    if hasattr(ai_record_msg, "reasoning_content"):
                        logger.info("🤯 Start Record Deep Thinking: ")
                        logger.info(ai_record_msg.reasoning_content)
                        logger.info("🤯 End Record Deep Thinking")
                    record_content = ai_record_msg.content
                    record_content = repair_json(record_content)
                    new_record_infos = json.loads(record_content)
                    history_infos.extend(new_record_infos)
            if agent_state and agent_state.is_stop_requested():
                # Stop
                break

        logger.info("\nFinish Searching, Start Generating Report...")

        # 5. Report Generation in Markdown (or JSON if you prefer)
        return await generate_final_report(task, history_infos, save_dir, llm)

    except Exception as e:
        logger.error(f"Deep research Error: {e}")
        return await generate_final_report(task, history_infos, save_dir, llm, str(e))
    finally:
        if browser:
            await browser.close()
        if browser_context:
            await browser_context.close()
        logger.info("Browser closed.")


async def generate_final_report(task, history_infos, save_dir, llm, error_msg=None):
    """Generate report from collected information with error handling"""
    try:
        logger.info("\nAttempting to generate final report from collected data...")

        writer_system_prompt = """
        You are a **Deep Researcher** and a professional report writer tasked with creating polished, high-quality reports that fully meet the user's needs, based on the user's instructions and the relevant information provided. You will write the report using Markdown format, ensuring it is both informative and visually appealing.

**Specific Instructions:**

*   **Structure for Impact:** The report must have a clear, logical, and impactful structure. Begin with a compelling introduction that immediately grabs the reader's attention. Develop well-structured body paragraphs that flow smoothly and logically, and conclude with a concise and memorable conclusion that summarizes key takeaways and leaves a lasting impression.
*   **Engaging and Vivid Language:** Employ precise, vivid, and descriptive language to make the report captivating and enjoyable to read. Use stylistic techniques to enhance engagement. Tailor your tone, vocabulary, and writing style to perfectly suit the subject matter and the intended audience to maximize impact and readability.
*   **Accuracy, Credibility, and Citations:** Ensure that all information presented is meticulously accurate, rigorously truthful, and robustly supported by the available data. **Cite sources exclusively using bracketed sequential numbers within the text (e.g., [1], [2], etc.). If no references are used, omit citations entirely.** These numbers must correspond to a numbered list of references at the end of the report.
*   **Publication-Ready Formatting:** Adhere strictly to Markdown formatting for excellent readability and a clean, highly professional visual appearance. Pay close attention to formatting details like headings, lists, emphasis, and spacing to optimize the visual presentation and reader experience. The report should be ready for immediate publication upon completion, requiring minimal to no further editing for style or format.
*   **Conciseness and Clarity (Unless Specified Otherwise):** When the user does not provide a specific length, prioritize concise and to-the-point writing, maximizing information density while maintaining clarity.
*   **Data-Driven Comparisons with Tables:**  **When appropriate and beneficial for enhancing clarity and impact, present data comparisons in well-structured Markdown tables. This is especially encouraged when dealing with numerical data or when a visual comparison can significantly improve the reader's understanding.**
*   **Length Adherence:** When the user specifies a length constraint, meticulously stay within reasonable bounds of that specification, ensuring the content is appropriately scaled without sacrificing quality or completeness.
*   **Comprehensive Instruction Following:** Pay meticulous attention to all details and nuances provided in the user instructions. Strive to fulfill every aspect of the user's request with the highest degree of accuracy and attention to detail, creating a report that not only meets but exceeds expectations for quality and professionalism.
*   **Reference List Formatting:** The reference list at the end must be formatted as follows:  
    `[1] Title (URL, if available)`
    **Each reference must be separated by a blank line to ensure proper spacing.** For example:

    ```
    [1] Title 1 (URL1, if available)

    [2] Title 2 (URL2, if available)
    ```
    **Furthermore, ensure that the reference list is free of duplicates. Each unique source should be listed only once, regardless of how many times it is cited in the text.**
*   **ABSOLUTE FINAL OUTPUT RESTRICTION:**  **Your output must contain ONLY the finished, publication-ready Markdown report. Do not include ANY extraneous text, phrases, preambles, meta-commentary, or markdown code indicators (e.g., "```markdown```"). The report should begin directly with the title and introductory paragraph, and end directly after the conclusion and the reference list (if applicable).**  **Your response will be deemed a failure if this instruction is not followed precisely.**
        
**Inputs:**

1. **User Instruction:** The original instruction given by the user. This helps you determine what kind of information will be useful and how to structure your thinking.
2. **Search Information:** Information gathered from the search queries.
        """

        history_infos_ = json.dumps(history_infos, indent=4)
        record_json_path = os.path.join(save_dir, "record_infos.json")
        logger.info(f"save All recorded information at {record_json_path}")
        with open(record_json_path, "w") as fw:
            json.dump(history_infos, fw, indent=4)
        report_prompt = f"User Instruction:{task} \n Search Information:\n {history_infos_}"
        report_messages = [SystemMessage(content=writer_system_prompt),
                           HumanMessage(content=report_prompt)]  # New context for report generation
        ai_report_msg = llm.invoke(report_messages)
        if hasattr(ai_report_msg, "reasoning_content"):
            logger.info("🤯 Start Report Deep Thinking: ")
            logger.info(ai_report_msg.reasoning_content)
            logger.info("🤯 End Report Deep Thinking")
        report_content = ai_report_msg.content
        report_content = re.sub(r"^```\s*markdown\s*|^\s*```|```\s*$", "", report_content, flags=re.MULTILINE)
        report_content = report_content.strip()

        # Add error notification to the report
        if error_msg:
            report_content = f"## ⚠️ Research Incomplete - Partial Results\n" \
                             f"**The research process was interrupted by an error:** {error_msg}\n\n" \
                             f"{report_content}"

        report_file_path = os.path.join(save_dir, "final_report.md")
        with open(report_file_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        logger.info(f"Save Report at: {report_file_path}")
        return report_content, report_file_path

    except Exception as report_error:
        logger.error(f"Failed to generate partial report: {report_error}")
        return f"Error generating report: {str(report_error)}", None
