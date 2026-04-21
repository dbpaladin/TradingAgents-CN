# TradingAgents/graph/signal_processing.py

import json
import re

from langchain_openai import ChatOpenAI

# 导入统一日志系统和图处理模块日志装饰器
from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_graph_module
from tradingagents.agents.utils.prompt_context import compact_text
logger = get_logger("graph.signal_processing")


class SignalProcessor:
    """Processes trading signals to extract actionable decisions."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize with an LLM for processing."""
        self.quick_thinking_llm = quick_thinking_llm

    @log_graph_module("signal_processing")
    def process_signal(self, full_signal: str, stock_symbol: str = None) -> dict:
        """
        Process a full trading signal to extract structured decision information.

        Args:
            full_signal: Complete trading signal text
            stock_symbol: Stock symbol to determine currency type

        Returns:
            Dictionary containing extracted decision information
        """

        # 验证输入参数
        if not full_signal or not isinstance(full_signal, str) or len(full_signal.strip()) == 0:
            logger.error(f"❌ [SignalProcessor] 输入信号为空或无效: {repr(full_signal)}")
            return {
                'action': '持有',
                'target_price': None,
                'confidence': 0.5,
                'risk_score': 0.5,
                'reasoning': '输入信号无效，默认持有建议'
            }

        # 清理和验证信号内容
        full_signal = full_signal.strip()
        full_signal = compact_text(full_signal, 1800, "signal_processing.full_signal")
        if len(full_signal) == 0:
            logger.error(f"❌ [SignalProcessor] 信号内容为空")
            return {
                'action': '持有',
                'target_price': None,
                'confidence': 0.5,
                'risk_score': 0.5,
                'reasoning': '信号内容为空，默认持有建议'
            }

        # 检测股票类型和货币
        from tradingagents.utils.stock_utils import StockUtils

        market_info = StockUtils.get_market_info(stock_symbol)
        is_china = market_info.get('is_china', True)
        currency = market_info.get('currency_name') or ('人民币' if is_china else '美元')
        currency_symbol = market_info.get('currency_symbol') or ('¥' if is_china else '$')
        current_price = self._extract_current_price(full_signal)

        market_name = market_info.get('market_name', '未知市场')
        logger.info(f"🔍 [SignalProcessor] 处理信号: 股票={stock_symbol}, 市场={market_name}, 货币={currency}",
                   extra={'stock_symbol': stock_symbol, 'market': market_name, 'currency': currency})

        messages = [
            (
                "system",
                f"""您是一位专业的金融分析助手，负责从交易员的分析报告中提取结构化的投资决策信息。

请从提供的分析报告中提取以下信息，并以JSON格式返回：

{{
    "action": "买入/持有/卖出",
    "target_price": 数字({currency}价格，**必须提供具体数值，不能为null**),
    "confidence": 数字(0-1之间，如果没有明确提及则为0.7),
    "risk_score": 数字(0-1之间，如果没有明确提及则为0.5),
    "reasoning": "决策的主要理由摘要"
}}

请确保：
1. action字段必须是"买入"、"持有"或"卖出"之一（绝对不允许使用英文buy/hold/sell）
2. target_price必须是具体的数字,target_price应该是合理的{currency}价格数字（使用{currency_symbol}符号）
3. confidence和risk_score应该在0-1之间
4. reasoning应该是简洁的中文摘要
5. 所有内容必须使用中文，不允许任何英文投资建议

特别注意：
- 股票代码 {stock_symbol or '未知'} 是{market_name}，使用{currency}计价
- 目标价格必须与股票的交易货币一致（{currency_symbol}）

如果某些信息在报告中没有明确提及，请使用合理的默认值。

输出要求：
- 只返回JSON，不要附加解释
- reasoning 控制在 60 字以内
""",
            ),
            ("human", full_signal),
        ]

        # 验证messages内容
        if not messages or len(messages) == 0:
            logger.error(f"❌ [SignalProcessor] messages为空")
            return self._get_default_decision()
        
        # 验证human消息内容
        human_content = messages[1][1] if len(messages) > 1 else ""
        if not human_content or len(human_content.strip()) == 0:
            logger.error(f"❌ [SignalProcessor] human消息内容为空")
            return self._get_default_decision()

        logger.debug(f"🔍 [SignalProcessor] 准备调用LLM，消息数量: {len(messages)}, 信号长度: {len(full_signal)}")

        try:
            response = self.quick_thinking_llm.bind(max_tokens=300, temperature=0).invoke(messages).content
            logger.debug(f"🔍 [SignalProcessor] LLM响应: {response[:200]}...")

            # 提取JSON部分
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_text = json_match.group()
                logger.debug(f"🔍 [SignalProcessor] 提取的JSON: {json_text}")
                decision_data = json.loads(json_text)

                # 验证和标准化数据
                action = self._normalize_action(decision_data.get('action', '持有'))
                explicit_action = self._extract_explicit_action(full_signal)
                if explicit_action:
                    action = explicit_action

                # 处理目标价格，确保正确提取
                target_price = self._normalize_price(decision_data.get('target_price'))
                reasoning = decision_data.get('reasoning', '')
                full_text = f"{reasoning} {full_signal}"
                extracted_target = self._extract_target_price(full_text)
                if extracted_target is not None:
                    target_price = extracted_target
                    logger.debug(f"🔍 [SignalProcessor] 从文本锚点提取核心目标价格: {target_price}")

                if target_price is None:
                    target_price = self._smart_price_estimation(full_text, action, is_china)
                    if target_price:
                        logger.debug(f"🔍 [SignalProcessor] 智能推算目标价格: {target_price}")
                    else:
                        logger.warning(f"🔍 [SignalProcessor] 未能提取到目标价格，设置为None")

                action, target_price, consistency_note = self._reconcile_action_and_target(
                    action=action,
                    target_price=target_price,
                    current_price=current_price,
                    text=full_signal,
                )
                execution_advice = self._extract_execution_advice(full_signal, action)

                result = {
                    'action': action,
                    'execution_advice': execution_advice,
                    'target_price': target_price,
                    'confidence': float(decision_data.get('confidence', 0.7)),
                    'risk_score': float(decision_data.get('risk_score', 0.5)),
                    'reasoning': decision_data.get('reasoning', '基于综合分析的投资建议'),
                    'current_price': current_price,
                    'consistency_note': consistency_note,
                }
                logger.info(f"🔍 [SignalProcessor] 处理结果: {result}",
                           extra={'action': result['action'], 'target_price': result['target_price'],
                                 'confidence': result['confidence'], 'stock_symbol': stock_symbol})
                return result
            else:
                # 如果无法解析JSON，使用简单的文本提取
                return self._extract_simple_decision(response, current_price=current_price, is_china=is_china)

        except Exception as e:
            logger.error(f"信号处理错误: {e}", exc_info=True, extra={'stock_symbol': stock_symbol})
            # 回退到简单提取
            return self._extract_simple_decision(full_signal, current_price=current_price, is_china=is_china)

    def _normalize_action(self, action: str) -> str:
        """将各种动作表达收敛为 买入/持有/卖出。"""
        if action in ['买入', '持有', '卖出']:
            return action

        action_map = {
            'buy': '买入', 'hold': '持有', 'sell': '卖出',
            'BUY': '买入', 'HOLD': '持有', 'SELL': '卖出',
            '购买': '买入', '保持': '持有', '出售': '卖出',
            'purchase': '买入', 'keep': '持有', 'dispose': '卖出'
        }
        return action_map.get(action, '持有')

    def _normalize_price(self, target_price) -> float:
        """标准化目标价格字段。"""
        try:
            if target_price is None or target_price in {"null", ""}:
                return None
            if isinstance(target_price, str):
                clean_price = (
                    target_price.replace('$', '')
                    .replace('¥', '')
                    .replace('￥', '')
                    .replace('元', '')
                    .replace('美元', '')
                    .strip()
                )
                return float(clean_price) if clean_price and clean_price.lower() not in ['none', 'null'] else None
            if isinstance(target_price, (int, float)):
                return float(target_price)
        except (ValueError, TypeError):
            logger.warning("🔍 [SignalProcessor] 价格转换失败，设置为None")
        return None

    def _extract_explicit_action(self, text: str) -> str:
        """优先读取原文中的最终建议，避免二次总结改写动作。"""
        patterns = [
            r'最终建议[：:]\s*(买入|持有|卖出)',
            r'建议[：:]\s*(买入|持有|卖出)',
            r'\*\*行动\*\*[：:]\s*(买入|持有|卖出)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _extract_execution_advice(self, text: str, action: str) -> str:
        """提取更细粒度的执行建议，避免被三分类动作压平。"""
        if not text or not isinstance(text, str):
            return ""

        normalized_lines = []
        for line in text.splitlines():
            stripped = re.sub(r"^[#>*\-\d\.\)\s]+", "", line).strip()
            if stripped:
                normalized_lines.append(stripped)

        holding_line = ""
        empty_line = ""
        generic_line = ""

        for line in normalized_lines:
            if not holding_line and re.search(r"持仓者建议[：:]", line):
                holding_line = line
            elif not empty_line and re.search(r"空仓者建议[：:]", line):
                empty_line = line
            elif not generic_line and re.search(r"(操作建议|执行建议|明确建议|立刻执行|战略行动)[：:]", line):
                generic_line = line

        advice_parts = []
        if holding_line:
            advice_parts.append(holding_line.replace("持仓者建议：", "持仓者：").replace("持仓者建议:", "持仓者："))
        if empty_line:
            advice_parts.append(empty_line.replace("空仓者建议：", "空仓者：").replace("空仓者建议:", "空仓者："))
        if advice_parts:
            return "；".join(advice_parts)

        if generic_line:
            match = re.search(r"(?:操作建议|执行建议|明确建议|立刻执行|战略行动)[：:]\s*(.+)", generic_line)
            if match:
                return match.group(1).strip()

        if action == "持有" and re.search(r"减仓观察|不追涨|等待确认|逢高兑现|降低仓位", text):
            return "持仓者减仓观察，空仓者等待确认"
        if action == "卖出" and re.search(r"减仓|清仓|分批卖出|逢高兑现", text):
            return "分批减仓或卖出，优先控制回撤"
        if action == "买入" and re.search(r"回踩|分批买入|小仓试错|突破再介入", text):
            return "等待合适位置后分批买入，避免一次性重仓"
        return ""

    def _extract_current_price(self, text: str) -> float:
        """从分析文本中提取当前价格/现价。"""
        current_price_patterns = [
            r'最新股价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'当前价格[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'当前股价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'当前价[格位]?[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'现价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'股价[：:]?\s*[¥\$]?(\d+(?:\.\d+)?)',
        ]
        for pattern in current_price_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _extract_target_price(self, text: str) -> float:
        """优先抓取核心/基准目标价，避免扫到普通价格数字。"""
        stop_loss_cues = ("止损", "风控位", "防守位", "支撑位", "跌破", "离场", "清仓")

        # 1. 先按行提取明确的核心/基准目标价，避免把“止损位”抓成目标价。
        explicit_line_patterns = [
            r'我的基准目标价(?:（[^）]*）)?(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'基准情景目标价(?:（[^）]*）)?(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'基准目标价(?:（[^）]*）)?(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'基准情景(?:（[^）]*）)?(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'核心目标价(?:（[^）]*）)?(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'核心参考价(?:（[^）]*）)?(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
        ]
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or any(cue in stripped for cue in stop_loss_cues):
                continue
            for pattern in explicit_line_patterns:
                match = re.search(pattern, stripped, re.IGNORECASE)
                if match:
                    try:
                        return float(match.group(1))
                    except ValueError:
                        continue

            # 处理“基准情景：¥60-70”这类区间写法，返回区间中值作为核心目标价。
            range_match = re.search(
                r'基准情景(?:（[^）]*）)?(?:[：:]|\s)?.*?[¥\$]?(\d+(?:\.\d+)?)\s*[-~–—至]+\s*[¥\$]?(\d+(?:\.\d+)?)',
                stripped,
                re.IGNORECASE,
            )
            if range_match:
                try:
                    low = float(range_match.group(1))
                    high = float(range_match.group(2))
                    return round((low + high) / 2, 2)
                except ValueError:
                    pass

        # 2. 再做全文兜底，但跳过明显带止损语义的命中。
        priority_patterns = [
            r'目标价位(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'目标价(?:[：:]|\s)?\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'看[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
            r'上涨[到至]\s*[¥\$]?(\d+(?:\.\d+)?)',
        ]
        for pattern in priority_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                context = text[max(0, match.start() - 24): min(len(text), match.end() + 24)]
                if any(cue in context for cue in stop_loss_cues):
                    continue
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _reconcile_action_and_target(
        self,
        action: str,
        target_price: float,
        current_price: float,
        text: str,
    ) -> tuple[str, float, str]:
        """修正动作与目标价显著冲突的情况。"""
        bearish_cues = bool(re.search(r'减仓|卖出|锁利|不追高|等待确认|观望|回撤到位再考虑', text))
        bullish_cues = bool(re.search(r'加仓|买入|回踩买入|顺势追随|突破再介入', text))
        strong_sell_execution_cues = bool(
            re.search(
                r'降到?0[\-–—~至]2成|降至0[\-–—~至]2成|降到?0–2成|降至0–2成|'
                r'优先减/清|继续逢高出清|分批出清|剩余仓位清掉|坚决空仓|反弹.*出清|'
                r'跌破.*清仓|清仓|空仓',
                text,
            )
        )

        if action == '持有' and strong_sell_execution_cues and not bullish_cues:
            logger.info("🔍 [SignalProcessor] 检测到持有标题但执行层要求显著降仓/出清，修正为卖出")
            note_price = f"{target_price:.2f}" if target_price is not None else "未提取"
            note_current = f"{current_price:.2f}" if current_price is not None else "未提取"
            return (
                '卖出',
                target_price,
                f"检测到原始动作为“持有”，但执行层要求显著降仓/出清（目标价 {note_price}，现价 {note_current}），已按实际交易语义修正为“卖出”。",
            )

        if current_price is None or target_price is None:
            return action, target_price, ""

        # 持有 + 明显低于现价的目标价，经常意味着“减仓/偏卖出”而不是中性持有。
        if action == '持有' and target_price < current_price * 0.97 and bearish_cues and not bullish_cues:
            logger.info(
                "🔍 [SignalProcessor] 检测到持有建议与偏空目标价冲突，按原文减仓/等待确认语义修正为卖出"
            )
            return (
                '卖出',
                target_price,
                f"检测到原始动作为“持有”，但目标价 {target_price:.2f} 低于现价 {current_price:.2f}，且原文含“减仓/等待确认”语义，已按原始风控语义修正为“卖出”。",
            )

        if action == '买入' and target_price < current_price * 0.97:
            logger.info("🔍 [SignalProcessor] 买入建议与偏低目标价冲突，修正为持有")
            return (
                '持有',
                current_price,
                f"检测到“买入”与目标价 {target_price:.2f} 明显低于现价 {current_price:.2f} 冲突，已回退为“持有/现价附近目标”。",
            )

        if action == '卖出' and target_price > current_price * 1.03 and bullish_cues:
            logger.info("🔍 [SignalProcessor] 卖出建议与偏高目标价冲突，修正为持有")
            return (
                '持有',
                current_price,
                f"检测到“卖出”与目标价 {target_price:.2f} 明显高于现价 {current_price:.2f} 冲突，且原文含偏多语义，已回退为“持有/现价附近目标”。",
            )

        return action, target_price, ""

    def _smart_price_estimation(self, text: str, action: str, is_china: bool) -> float:
        """智能价格推算方法"""
        # 尝试从文本中提取当前价格和涨跌幅信息
        current_price = self._extract_current_price(text)
        percentage_change = None

        # 提取涨跌幅信息
        percentage_patterns = [
            r'上涨\s*(\d+(?:\.\d+)?)%',
            r'涨幅\s*(\d+(?:\.\d+)?)%',
            r'增长\s*(\d+(?:\.\d+)?)%',
            r'(\d+(?:\.\d+)?)%\s*的?上涨',
        ]
        
        for pattern in percentage_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    percentage_change = float(match.group(1)) / 100
                    break
                except ValueError:
                    continue
        
        # 基于动作和信息推算目标价
        if current_price and percentage_change:
            if action == '买入':
                return round(current_price * (1 + percentage_change), 2)
            elif action == '卖出':
                return round(current_price * (1 - percentage_change), 2)
        
        # 如果有当前价格但没有涨跌幅，使用默认估算
        if current_price:
            if action == '买入':
                # 买入建议默认10-20%涨幅
                multiplier = 1.15 if is_china else 1.12
                return round(current_price * multiplier, 2)
            elif action == '卖出':
                # 卖出建议默认5-10%跌幅
                multiplier = 0.95 if is_china else 0.92
                return round(current_price * multiplier, 2)
            else:  # 持有
                # 持有建议使用当前价格
                return current_price
        
        return None

    def _extract_simple_decision(self, text: str, current_price: float = None, is_china: bool = True) -> dict:
        """简单的决策提取方法作为备用"""
        # 提取动作
        action = self._extract_explicit_action(text) or '持有'
        if action == '持有' and re.search(r'买入|BUY', text, re.IGNORECASE):
            action = '买入'
        elif action == '持有' and re.search(r'卖出|SELL', text, re.IGNORECASE):
            action = '卖出'

        # 尝试提取目标价格（使用增强的模式）
        target_price = self._extract_target_price(text)

        # 如果没有找到价格，尝试智能推算
        if target_price is None:
            target_price = self._smart_price_estimation(text, action, is_china)

        action, target_price, consistency_note = self._reconcile_action_and_target(
            action=action,
            target_price=target_price,
            current_price=current_price or self._extract_current_price(text),
            text=text,
        )

        return {
            'action': action,
            'execution_advice': self._extract_execution_advice(text, action),
            'target_price': target_price,
            'confidence': 0.7,
            'risk_score': 0.5,
            'reasoning': '基于综合分析的投资建议',
            'current_price': current_price or self._extract_current_price(text),
            'consistency_note': consistency_note,
        }

    def _get_default_decision(self) -> dict:
        """返回默认的投资决策"""
        return {
            'action': '持有',
            'execution_advice': '',
            'target_price': None,
            'confidence': 0.5,
            'risk_score': 0.5,
            'reasoning': '输入数据无效，默认持有建议'
        }
