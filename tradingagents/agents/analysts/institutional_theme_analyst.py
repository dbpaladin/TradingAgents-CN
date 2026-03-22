from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("analysts.institutional_theme")


def create_institutional_theme_analyst(llm, toolkit):
    @log_analyst_module("institutional_theme")
    def institutional_theme_analyst_node(state):
        tool_call_count = state.get("institutional_theme_tool_call_count", 0)
        max_tool_calls = 3
        logger.info(f"🔧 [机构布局题材分析师] 当前工具调用次数: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        tools = [toolkit.get_a_share_institutional_theme_opportunities]

        system_message = (
            """您是一位专注A股“机构提前布局题材”识别的分析师。

您的任务不是追逐已经完全爆发的热点，而是识别：
1. 机构可能正在准备布局的题材
2. 已经出现试盘痕迹、但还未全面一致的方向
3. 目标股是否属于这些候选题材的先手核心、试盘前排或边缘观察对象

分析要求：
- 必须区分“当前主线热点”和“前瞻候选题材”
- 必须判断题材处于酝酿期、试盘期、扩散期还是观察期
- 必须指出目标股是否适合提前布局，而不是只给模糊建议
- 必须明确写出适合先手跟踪的题材与不宜提前埋伏的题材
- 不要把已经高潮一致的题材误写成提前布局机会
- 如果目标股与热门板块存在产业链或业务关联，但不在候选先手名单中，必须写成“有板块关联但不属于候选先手核心”，禁止偷换成“无题材关联”
- 若给出“机构布局评分”，必须补充评分解释，至少说明：评分来自哪些维度、当前分数落在哪个区间、为什么不足以支持提前布局
- 当新闻催化、机构席位、量价试盘、强势池命中等关键证据缺失时，必须明确标注“数据缺口/证据不足”，并降低结论强度

输出结构要求：
1. 前瞻候选题材梳理
2. 目标股与热点板块/候选题材的关系
3. 机构布局评分与评分解释
4. 数据缺口与置信度
5. 交易建议（区分“适合提前布局”和“仅观察不布局”）

请用中文输出详细分析，并在末尾附上简洁 Markdown 表格总结。"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一位有用的AI助手，与其他分析师协作。"
                    " 使用提供的工具来推进回答问题。"
                    " 如果您无法完全回答，没关系；其他分析师会继续补充。"
                    " 您可以访问以下工具：{tool_names}。\n{system_message}"
                    "当前日期是{current_date}，分析标的是{ticker}。请用中文撰写所有分析内容。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        tool_names = []
        for tool in tools:
            if hasattr(tool, "name"):
                tool_names.append(tool.name)
            elif hasattr(tool, "__name__"):
                tool_names.append(tool.__name__)
            else:
                tool_names.append(str(tool))

        prompt = prompt.partial(tool_names=", ".join(tool_names))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke({"messages": state["messages"]})

        if GoogleToolCallHandler.is_google_model(llm):
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=ticker,
                analyst_type="A股机构布局题材分析",
                specific_requirements="重点关注题材酝酿、试盘痕迹、候选先手方向以及目标股是否适合提前布局。",
            )
            report, _messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="机构布局题材分析师",
            )
        else:
            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

        return {
            "messages": [result],
            "institutional_theme_report": report,
            "institutional_theme_tool_call_count": tool_call_count + 1,
        }

    return institutional_theme_analyst_node
