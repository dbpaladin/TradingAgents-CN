import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.prompt_context import compact_history, compact_text, format_memories
logger = get_logger("default")


def create_risk_manager(llm, memory):
    def risk_manager_node(state) -> dict:

        company_name = state["company_of_interest"]

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        market_research_report = state["market_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]
        a_share_sentiment_report = state.get("a_share_sentiment_report", "")
        fund_flow_report = state.get("fund_flow_report", "")
        theme_rotation_report = state.get("theme_rotation_report", "")
        institutional_theme_report = state.get("institutional_theme_report", "")
        sentiment_report = state["sentiment_report"]
        trader_plan = state["investment_plan"]

        market_research_report = compact_text(market_research_report, 1200, "risk_manager.market_report")
        a_share_sentiment_report = compact_text(a_share_sentiment_report, 700, "risk_manager.a_share_sentiment")
        fund_flow_report = compact_text(fund_flow_report, 700, "risk_manager.fund_flow")
        theme_rotation_report = compact_text(theme_rotation_report, 800, "risk_manager.theme_rotation")
        institutional_theme_report = compact_text(institutional_theme_report, 800, "risk_manager.institutional_theme")
        sentiment_report = compact_text(sentiment_report, 400, "risk_manager.sentiment")
        news_report = compact_text(news_report, 500, "risk_manager.news")
        fundamentals_report = compact_text(fundamentals_report, 900, "risk_manager.fundamentals")
        trader_plan = compact_text(trader_plan, 700, "risk_manager.trader_plan")
        history = compact_history(history, 800, "risk_manager.history")

        curr_situation = f"{market_research_report}\n\n{a_share_sentiment_report}\n\n{fund_flow_report}\n\n{theme_rotation_report}\n\n{institutional_theme_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 安全检查：确保memory不为None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = format_memories(past_memories, max_chars=700, label="risk_manager.memories")

        prompt = f"""
作为风险管理委员会主席，请评估三位风险分析师的辩论，并确定交易员方案的最终处理意见。

你的目标：
1. 明确给出最终建议：买入、卖出或持有。
2. 只提炼最关键的风险与修正意见，不要复述整段辩论。
3. 如果是A股，必须结合题材轮动和机构布局题材判断交易逻辑是否成立。
4. 参考过去经验教训，避免重复误判。

过去经验：
{past_memory_str}

分析师辩论历史：
{history}

关键背景报告：
市场研究：{market_research_report}
A股盘面情绪：{a_share_sentiment_report}
A股资金面：{fund_flow_report}
A股题材轮动：{theme_rotation_report}
机构布局题材：{institutional_theme_report}
公共舆情：{sentiment_report}
新闻事件：{news_report}
基本面：{fundamentals_report}
交易员原始计划：{trader_plan}

输出要求：
- 第一行先写“最终建议：买入/卖出/持有”
- 第二部分必须写“决策解释：”，用 1-2 句话说明为什么最终结论可以覆盖子模块分歧；如果基本面、题材、资金面之间存在冲突，必须显式解释“谁压过了谁，为什么”
- 再写不超过 3 条最关键的风险与修正意见
- 必须单独给出“持仓者建议”和“空仓者建议”，避免一刀切
- 必须给出一个核心目标价和一个核心止损/风控位
- 必须同时给出保守/基准/乐观三种估值情景，并明确“基准情景目标价”作为核心目标价
- 如果题材轮动报告显示“主线相关但非核心”，不得偷换成“无主线关联”
- 如果北向、融资、机构席位等关键资金数据缺失，必须承认“资金证据不完整”，不能把缺失数据表述成强结论
- “资金证据不完整”默认只降低结论强度，不足以单独推翻已有的正面基本面/题材/资金证据；若因此转向保守，必须明确写出还有哪些负面证据共同支持
- 如果资金面报告明确提示“低样本弱证据”或“日期未对齐”，必须承认该证据不能单独主导最终裁决
- 如果技术/情绪偏强，但基本面、题材、资金面出现明显冲突，默认结论应收敛为“持仓者减仓观察 / 空仓者等待确认”，而不是直接一刀切卖出
- 只有在至少两类独立负面证据同时成立时，才适合维持明确卖出结论；否则应优先给出保守持有或等待确认
- 如果最终建议与基本面建议相反，必须明确写出“基本面逻辑为何暂时失效”
- 总长度控制在 500 字以内
- 全部使用中文
"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        # 粗略估算 token 数量（中文约 1.5-2 字符/token，英文约 4 字符/token）
        estimated_tokens = int(prompt_length / 1.8)  # 保守估计

        logger.info(f"📊 [Risk Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 交易员计划长度: {len(trader_plan)} 字符")
        logger.info(f"   - 历史记忆长度: {len(past_memory_str)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # 增强的LLM调用，包含错误处理和重试机制
        max_retries = 3
        retry_count = 0
        response_content = ""

        while retry_count < max_retries:
            try:
                logger.info(f"🔄 [Risk Manager] 调用LLM生成交易决策 (尝试 {retry_count + 1}/{max_retries})")

                # ⏱️ 记录开始时间
                start_time = time.time()

                response = llm.bind(max_tokens=650, temperature=0.2).invoke(prompt)

                # ⏱️ 记录结束时间
                elapsed_time = time.time() - start_time
                
                if response and hasattr(response, 'content') and response.content:
                    response_content = response.content.strip()

                    # 📊 统计响应信息
                    response_length = len(response_content)
                    estimated_output_tokens = int(response_length / 1.8)

                    # 尝试获取实际的 token 使用情况（如果 LLM 返回了）
                    usage_info = ""
                    if hasattr(response, 'response_metadata') and response.response_metadata:
                        metadata = response.response_metadata
                        if 'token_usage' in metadata:
                            token_usage = metadata['token_usage']
                            usage_info = f", 实际Token: 输入={token_usage.get('prompt_tokens', 'N/A')} 输出={token_usage.get('completion_tokens', 'N/A')} 总计={token_usage.get('total_tokens', 'N/A')}"

                    logger.info(f"⏱️ [Risk Manager] LLM调用耗时: {elapsed_time:.2f}秒")
                    logger.info(f"📊 [Risk Manager] 响应统计: {response_length} 字符, 估算~{estimated_output_tokens} tokens{usage_info}")

                    if len(response_content) > 10:  # 确保响应有实质内容
                        logger.info(f"✅ [Risk Manager] LLM调用成功")
                        break
                    else:
                        logger.warning(f"⚠️ [Risk Manager] LLM响应内容过短: {len(response_content)} 字符")
                        response_content = ""
                else:
                    logger.warning(f"⚠️ [Risk Manager] LLM响应为空或无效")
                    response_content = ""

            except Exception as e:
                elapsed_time = time.time() - start_time
                logger.error(f"❌ [Risk Manager] LLM调用失败 (尝试 {retry_count + 1}): {str(e)}")
                logger.error(f"⏱️ [Risk Manager] 失败前耗时: {elapsed_time:.2f}秒")
                response_content = ""
            
            retry_count += 1
            if retry_count < max_retries and not response_content:
                logger.info(f"🔄 [Risk Manager] 等待2秒后重试...")
                time.sleep(2)
        
        # 如果所有重试都失败，生成默认决策
        if not response_content:
            logger.error(f"❌ [Risk Manager] 所有LLM调用尝试失败，使用默认决策")
            response_content = f"""**默认建议：持有**

由于技术原因无法生成详细分析，基于当前市场状况和风险控制原则，建议对{company_name}采取持有策略。

**理由：**
1. 市场信息不足，避免盲目操作
2. 保持现有仓位，等待更明确的市场信号
3. 控制风险，避免在不确定性高的情况下做出激进决策

**建议：**
- 密切关注市场动态和公司基本面变化
- 设置合理的止损和止盈位
- 等待更好的入场或出场时机

注意：此为系统默认建议，建议结合人工分析做出最终决策。"""

        new_risk_debate_state = {
            "judge_decision": response_content,
            "history": risk_debate_state["history"],
            "risky_history": risk_debate_state["risky_history"],
            "safe_history": risk_debate_state["safe_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_risky_response": risk_debate_state["current_risky_response"],
            "current_safe_response": risk_debate_state["current_safe_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        logger.info(f"📋 [Risk Manager] 最终决策生成完成，内容长度: {len(response_content)} 字符")
        
        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": response_content,
        }

    return risk_manager_node
