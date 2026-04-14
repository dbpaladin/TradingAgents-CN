#!/usr/bin/env python3
"""
中国财经数据聚合工具
优先复用项目内已接入的新闻/缓存数据源，避免占位新闻导致样本失真。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Iterable
import re

from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")


class ChineseFinanceDataAggregator:
    """中国财经数据聚合器"""

    def __init__(self):
        self.max_news_items = 60

    def get_stock_sentiment_summary(self, ticker: str, days: int = 7) -> Dict:
        """
        获取股票情绪分析汇总
        整合项目内可获取的中国财经数据源
        """
        try:
            # 1. 获取财经新闻情绪
            news_sentiment = self._get_finance_news_sentiment(ticker, days)

            # 2. 获取论坛/社媒情绪（优先Mongo缓存，缺失时不再伪造样本）
            forum_sentiment = self._get_stock_forum_sentiment(ticker, days)

            # 3. 获取媒体覆盖面
            media_sentiment = self._get_media_coverage_sentiment(ticker, days)

            # 4. 综合分析
            overall_sentiment = self._calculate_overall_sentiment(
                news_sentiment, forum_sentiment, media_sentiment
            )

            return {
                "ticker": ticker,
                "analysis_period": f"{days} days",
                "overall_sentiment": overall_sentiment,
                "news_sentiment": news_sentiment,
                "forum_sentiment": forum_sentiment,
                "media_sentiment": media_sentiment,
                "summary": self._generate_sentiment_summary(overall_sentiment),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"[中文情绪] 汇总失败: {ticker} - {e}", exc_info=True)
            return {
                "ticker": ticker,
                "error": f"数据获取失败: {str(e)}",
                "fallback_message": "新闻与社媒数据获取异常，建议结合基本面和技术面交叉验证",
                "timestamp": datetime.now().isoformat(),
            }

    def _get_finance_news_sentiment(self, ticker: str, days: int) -> Dict:
        """获取财经新闻情绪分析"""
        try:
            news_items = self._search_finance_news(ticker, days)

            positive_count = 0
            negative_count = 0
            neutral_count = 0

            for item in news_items:
                text = f"{item.get('title', '')} {item.get('content', '')}".strip()
                sentiment = self._analyze_text_sentiment(text)
                if sentiment > 0.1:
                    positive_count += 1
                elif sentiment < -0.1:
                    negative_count += 1
                else:
                    neutral_count += 1

            total = len(news_items)
            if total == 0:
                return {
                    "sentiment_score": 0,
                    "confidence": 0,
                    "news_count": 0,
                    "source_count": 0,
                    "sample_titles": [],
                }

            sentiment_score = (positive_count - negative_count) / total
            unique_sources = sorted(
                {
                    str(item.get("source", "")).strip()
                    for item in news_items
                    if str(item.get("source", "")).strip()
                }
            )

            # 样本数和来源数共同决定置信度，避免单一来源高估可信度。
            confidence = min(total / 12, 1.0) * 0.7 + min(len(unique_sources) / 4, 1.0) * 0.3

            return {
                "sentiment_score": sentiment_score,
                "positive_ratio": positive_count / total,
                "negative_ratio": negative_count / total,
                "neutral_ratio": neutral_count / total,
                "news_count": total,
                "source_count": len(unique_sources),
                "sources": unique_sources,
                "sample_titles": [item.get("title", "") for item in news_items[:3] if item.get("title")],
                "confidence": confidence,
            }

        except Exception as e:
            logger.warning(f"[中文情绪] 财经新闻情绪获取失败: {ticker} - {e}")
            return {"error": str(e), "sentiment_score": 0, "confidence": 0, "news_count": 0}

    def _get_stock_forum_sentiment(self, ticker: str, days: int) -> Dict:
        """获取论坛/社媒情绪"""
        try:
            social_items = self._get_social_media_items(ticker, days)
            if not social_items:
                return {
                    "sentiment_score": 0,
                    "discussion_count": 0,
                    "hot_topics": [],
                    "sample_titles": [],
                    "platform_breakdown": {},
                    "extreme_ratio": 0.0,
                    "heat_level": "低热度",
                    "note": "未获取到有效社媒/论坛缓存数据，当前论坛情绪不计入加权",
                    "confidence": 0,
                }

            scores = []
            hot_topics = []
            sample_titles: List[str] = []
            platform_counter: Dict[str, int] = {}
            extreme_count = 0
            for item in social_items:
                text = " ".join(
                    str(item.get(field, "")).strip()
                    for field in ("title", "content", "text", "summary")
                ).strip()
                if not text:
                    continue
                if len(sample_titles) < 6:
                    sample_titles.append(str(item.get("title") or text[:80]))
                scores.append(self._analyze_text_sentiment(text))
                hot_topics.extend(self._extract_hot_topics(text))
                platform = str(item.get("platform") or item.get("source") or "unknown").strip()
                platform_counter[platform] = platform_counter.get(platform, 0) + 1
                if self._contains_extreme_word(text):
                    extreme_count += 1

            if not scores:
                return {
                    "sentiment_score": 0,
                    "discussion_count": len(social_items),
                    "hot_topics": [],
                    "sample_titles": sample_titles,
                    "platform_breakdown": platform_counter,
                    "extreme_ratio": 0.0,
                    "heat_level": self._classify_heat_level(len(social_items)),
                    "confidence": 0,
                }

            unique_topics = []
            for topic in hot_topics:
                if topic not in unique_topics:
                    unique_topics.append(topic)

            discussion_count = len(social_items)
            extreme_ratio = extreme_count / max(len(scores), 1)
            return {
                "sentiment_score": sum(scores) / len(scores),
                "discussion_count": discussion_count,
                "hot_topics": unique_topics[:5],
                "sample_titles": sample_titles,
                "platform_breakdown": platform_counter,
                "extreme_ratio": extreme_ratio,
                "heat_level": self._classify_heat_level(discussion_count),
                "confidence": min(len(scores) / 20, 1.0),
            }

        except Exception as e:
            logger.warning(f"[中文情绪] 论坛情绪获取失败: {ticker} - {e}")
            return {"error": str(e), "sentiment_score": 0, "confidence": 0}

    def _get_media_coverage_sentiment(self, ticker: str, days: int) -> Dict:
        """获取媒体报道情绪"""
        try:
            coverage_items = self._get_media_coverage(ticker, days)
            if not coverage_items:
                return {"sentiment_score": 0, "coverage_count": 0, "source_count": 0, "confidence": 0}

            sentiment_scores = []
            sources = set()
            for item in coverage_items:
                score = self._analyze_text_sentiment(
                    f"{item.get('title', '')} {item.get('summary', item.get('content', ''))}"
                )
                sentiment_scores.append(score)
                source = str(item.get("source", "")).strip()
                if source:
                    sources.add(source)

            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0

            return {
                "sentiment_score": avg_sentiment,
                "coverage_count": len(coverage_items),
                "source_count": len(sources),
                "confidence": min(len(coverage_items) / 10, 1.0) * 0.7 + min(len(sources) / 4, 1.0) * 0.3,
            }

        except Exception as e:
            logger.warning(f"[中文情绪] 媒体覆盖情绪获取失败: {ticker} - {e}")
            return {"error": str(e), "sentiment_score": 0, "confidence": 0}

    def _search_finance_news(self, ticker: str, days: int) -> List[Dict]:
        """搜索财经新闻，优先使用项目内真实数据源"""
        company_name = self._get_company_chinese_name(ticker)
        aliases = [ticker]
        if company_name:
            aliases.extend(self._expand_company_aliases(company_name))

        news_items = self._fetch_news_items(ticker, days)
        filtered_items = self._filter_news_by_aliases(news_items, aliases)

        if filtered_items:
            return filtered_items

        # 若过滤后为空，保留原始结果前若干条，避免严格过滤导致样本清零。
        return news_items[: min(len(news_items), 20)]

    def _fetch_news_items(self, ticker: str, days: int) -> List[Dict]:
        """汇总Mongo缓存和适配器新闻数据，并做统一归一化/去重"""
        hours_back = max(days * 24, 24)
        items: List[Dict] = []

        # 1. Mongo新闻缓存
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()
            mongo_items = adapter.get_news_data(ticker, hours_back=hours_back, limit=self.max_news_items)
            if mongo_items:
                items.extend(self._normalize_news_items(mongo_items, default_source="mongodb"))
        except Exception as e:
            logger.debug(f"[中文情绪] Mongo新闻读取失败: {e}")

        # 2. 数据源管理器（AKShare/Tushare/BaoStock fallback）
        try:
            from app.services.data_sources.manager import DataSourceManager

            manager = DataSourceManager()
            fetched_items, source = manager.get_news_with_fallback(
                code=str(ticker).zfill(6),
                days=days,
                limit=self.max_news_items,
                include_announcements=True,
                preferred_sources=["akshare", "baostock", "tushare"],
            )
            if fetched_items:
                items.extend(self._normalize_news_items(fetched_items, default_source=source or "fallback"))
        except Exception as e:
            logger.debug(f"[中文情绪] 适配器新闻读取失败: {e}")

        items = self._deduplicate_news_items(items)
        items.sort(key=lambda item: item.get("_sort_time") or datetime.min, reverse=True)
        return items[: self.max_news_items]

    def _get_media_coverage(self, ticker: str, days: int) -> List[Dict]:
        """获取媒体报道，复用新闻数据但聚焦媒体来源"""
        news_items = self._fetch_news_items(ticker, days)
        media_items = []
        for item in news_items:
            source = str(item.get("source", "")).lower()
            if any(keyword in source for keyword in ("证券", "财经", "财联", "新浪", "东方财富", "eastmoney", "akshare", "baostock", "tushare")):
                media_items.append(item)
        return media_items if media_items else news_items

    def _get_social_media_items(self, ticker: str, days: int) -> List[Dict]:
        """获取社媒/论坛缓存数据"""
        normalized_ticker = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)

        # 1. 优先读取 MongoDB 社媒缓存
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()
            items = adapter.get_social_media_data(normalized_ticker, hours_back=max(days * 24, 24), limit=80)
            if items:
                return self._normalize_news_items(items, default_source="social_cache")
        except Exception as e:
            logger.debug(f"[中文情绪] 社媒缓存读取失败: {e}")

        # 2. 缓存为空时，尝试实时抓取公开论坛（默认开启）
        live_enabled = os.getenv("CN_SOCIAL_LIVE_FETCH_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        if live_enabled:
            try:
                from tradingagents.dataflows.news.cn_social_sentiment import fetch_cn_social_posts

                company_name = self._get_company_chinese_name(ticker) or ""
                live_items = fetch_cn_social_posts(
                    ticker=normalized_ticker,
                    company_name=company_name,
                    max_posts_per_source=40,
                )
                if live_items:
                    logger.info(f"[中文情绪] 实时抓取社媒样本成功: {len(live_items)} 条")
                    return self._normalize_news_items(live_items, default_source="social_live")
            except Exception as e:
                logger.debug(f"[中文情绪] 实时社媒抓取失败: {e}")
        return []

    def _normalize_news_items(self, items: Iterable[Dict], default_source: str) -> List[Dict]:
        normalized = []
        for item in items:
            title = str(item.get("title") or item.get("新闻标题") or item.get("标题") or "").strip()
            content = str(
                item.get("content")
                or item.get("summary")
                or item.get("新闻内容")
                or item.get("text")
                or ""
            ).strip()
            source = str(
                item.get("source")
                or item.get("文章来源")
                or item.get("来源")
                or default_source
            ).strip() or default_source
            publish_time = (
                item.get("publish_time")
                or item.get("time")
                or item.get("发布时间")
                or item.get("created_at")
            )
            url = str(item.get("url") or item.get("新闻链接") or "").strip()
            item_type = str(item.get("type") or "news").strip()
            platform = str(item.get("platform") or "").strip()

            if not title and not content:
                continue

            normalized.append(
                {
                    "title": title,
                    "content": content,
                    "summary": content,
                    "source": source,
                    "platform": platform,
                    "publish_time": str(publish_time or ""),
                    "_sort_time": self._parse_datetime(publish_time),
                    "url": url,
                    "type": item_type,
                }
            )
        return normalized

    def _deduplicate_news_items(self, items: Iterable[Dict]) -> List[Dict]:
        deduped: List[Dict] = []
        seen = set()
        for item in items:
            title = re.sub(r"\s+", "", str(item.get("title", "")).lower())
            url = str(item.get("url", "")).strip()
            key = (title[:120], url)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _filter_news_by_aliases(self, items: Iterable[Dict], aliases: List[str]) -> List[Dict]:
        valid_aliases = [alias.strip().lower() for alias in aliases if alias and alias.strip()]
        if not valid_aliases:
            return list(items)

        filtered = []
        for item in items:
            haystack = " ".join(
                [
                    str(item.get("title", "")).lower(),
                    str(item.get("content", "")).lower(),
                    str(item.get("summary", "")).lower(),
                ]
            )
            if any(alias in haystack for alias in valid_aliases):
                filtered.append(item)
        return filtered

    def _expand_company_aliases(self, company_name: str) -> List[str]:
        aliases = {company_name}
        aliases.add(company_name.replace("股份有限公司", ""))
        aliases.add(company_name.replace("有限公司", ""))
        aliases.add(company_name.replace("集团", ""))
        return [alias for alias in aliases if alias]

    def _extract_hot_topics(self, text: str) -> List[str]:
        candidates = ["订单", "业绩", "分红", "回购", "中标", "政策", "新能源", "基建", "风险", "利润"]
        return [candidate for candidate in candidates if candidate in text]

    def _analyze_text_sentiment(self, text: str) -> float:
        """简单的中文文本情绪分析"""
        if not text:
            return 0

        positive_words = [
            "上涨", "增长", "利好", "看好", "买入", "推荐", "强势", "突破",
            "创新高", "中标", "增持", "回购", "高分红", "超预期",
        ]
        negative_words = [
            "下跌", "下降", "利空", "看空", "卖出", "风险", "跌破", "创新低",
            "亏损", "减持", "违约", "诉讼", "承压", "暴跌",
        ]

        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)

        if positive_count + negative_count == 0:
            return 0

        return (positive_count - negative_count) / (positive_count + negative_count)

    def _contains_extreme_word(self, text: str) -> bool:
        extreme_words = ["梭哈", "满仓", "all in", "清仓", "快跑", "垃圾", "必涨", "退市", "暴雷", "血亏", "无脑"]
        content = (text or "").lower()
        return any(word in content for word in extreme_words)

    def _classify_heat_level(self, sample_count: int) -> str:
        if sample_count >= 60:
            return "爆发"
        if sample_count >= 25:
            return "升温"
        if sample_count >= 10:
            return "平稳"
        return "低热度"

    def _get_company_chinese_name(self, ticker: str) -> Optional[str]:
        """获取公司中文名称"""
        try:
            from tradingagents.dataflows.cache.mongodb_cache_adapter import get_mongodb_cache_adapter

            adapter = get_mongodb_cache_adapter()
            stock_info = adapter.get_stock_basic_info(ticker)
            if stock_info:
                for key in ("name", "stock_name", "company_name"):
                    value = stock_info.get(key)
                    if value:
                        return str(value).strip()
        except Exception as e:
            logger.debug(f"[中文情绪] 从Mongo获取公司名失败: {e}")

        try:
            from tradingagents.dataflows.interface import get_china_stock_info_unified

            stock_info_text = get_china_stock_info_unified(ticker)
            match = re.search(r"股票名称:\s*(.+)", stock_info_text or "")
            if match:
                return match.group(1).strip()
        except Exception as e:
            logger.debug(f"[中文情绪] 从统一接口获取公司名失败: {e}")

        name_mapping = {
            "AAPL": "苹果",
            "TSLA": "特斯拉",
            "NVDA": "英伟达",
            "MSFT": "微软",
            "GOOGL": "谷歌",
            "AMZN": "亚马逊",
        }
        return name_mapping.get(ticker.upper())

    def _calculate_overall_sentiment(self, news_sentiment: Dict, forum_sentiment: Dict, media_sentiment: Dict) -> Dict:
        """计算综合情绪分析"""
        news_weight = news_sentiment.get("confidence", 0)
        forum_weight = forum_sentiment.get("confidence", 0)
        media_weight = media_sentiment.get("confidence", 0)

        total_weight = news_weight + forum_weight + media_weight
        total_samples = (
            news_sentiment.get("news_count", 0)
            + forum_sentiment.get("discussion_count", 0)
            + media_sentiment.get("coverage_count", 0)
        )

        if total_weight == 0:
            return {"sentiment_score": 0, "confidence": 0, "level": "neutral", "sample_size": total_samples}

        weighted_sentiment = (
            news_sentiment.get("sentiment_score", 0) * news_weight
            + forum_sentiment.get("sentiment_score", 0) * forum_weight
            + media_sentiment.get("sentiment_score", 0) * media_weight
        ) / total_weight

        if weighted_sentiment > 0.3:
            level = "very_positive"
        elif weighted_sentiment > 0.1:
            level = "positive"
        elif weighted_sentiment > -0.1:
            level = "neutral"
        elif weighted_sentiment > -0.3:
            level = "negative"
        else:
            level = "very_negative"

        return {
            "sentiment_score": weighted_sentiment,
            "confidence": min(total_weight / 3, 1.0),
            "level": level,
            "sample_size": total_samples,
        }

    def _generate_sentiment_summary(self, overall_sentiment: Dict) -> str:
        """生成情绪分析摘要"""
        level = overall_sentiment.get("level", "neutral")
        score = overall_sentiment.get("sentiment_score", 0)
        confidence = overall_sentiment.get("confidence", 0)
        sample_size = overall_sentiment.get("sample_size", 0)

        level_descriptions = {
            "very_positive": "非常积极",
            "positive": "积极",
            "neutral": "中性",
            "negative": "消极",
            "very_negative": "非常消极",
        }

        description = level_descriptions.get(level, "中性")
        confidence_level = "高" if confidence > 0.7 else "中" if confidence > 0.3 else "低"

        sample_note = ""
        if sample_size < 3:
            sample_note = "，样本偏少"
        elif sample_size < 10:
            sample_note = "，样本中等"

        return f"市场情绪: {description} (评分: {score:.2f}, 置信度: {confidence_level}{sample_note})"

    def _parse_datetime(self, value) -> Optional[datetime]:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None

        # 兼容 ISO / 日期字符串。
        for candidate in (text.replace("Z", "+00:00"), text):
            try:
                return datetime.fromisoformat(candidate)
            except Exception:
                pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                continue
        return None


def get_chinese_social_sentiment(ticker: str, curr_date: str) -> str:
    """
    获取中国社交媒体情绪分析的主要接口函数
    """
    aggregator = ChineseFinanceDataAggregator()

    try:
        sentiment_data = aggregator.get_stock_sentiment_summary(ticker, days=7)

        if "error" in sentiment_data:
            return f"""
中国市场情绪分析报告 - {ticker}
分析日期: {curr_date}

⚠️ 数据获取限制说明:
{sentiment_data.get('fallback_message', '数据获取遇到技术限制')}

建议:
1. 重点关注财经新闻和基本面分析
2. 参考官方财报和业绩指导
3. 关注行业政策和监管动态
4. 结合技术走势进行二次验证

注: 当前报告优先使用项目内缓存和公开财经新闻数据源。
"""

        overall = sentiment_data.get("overall_sentiment", {})
        news = sentiment_data.get("news_sentiment", {})
        forum = sentiment_data.get("forum_sentiment", {})
        media = sentiment_data.get("media_sentiment", {})

        sample_titles = news.get("sample_titles", [])
        sample_titles_text = "\n".join(f"- {title}" for title in sample_titles) if sample_titles else "- 暂无样本标题"
        forum_titles = forum.get("sample_titles", [])
        forum_titles_text = "\n".join(f"- {title}" for title in forum_titles) if forum_titles else "- 暂无社媒标题样本"
        platform_breakdown = forum.get("platform_breakdown", {})
        platform_breakdown_text = (
            "、".join(f"{k}:{v}" for k, v in platform_breakdown.items()) if platform_breakdown else "暂无"
        )

        return f"""
中国市场情绪分析报告 - {ticker}
分析日期: {curr_date}
分析周期: {sentiment_data.get('analysis_period', '7天')}

📊 综合情绪评估:
{sentiment_data.get('summary', '数据不足')}

📰 财经新闻情绪:
- 情绪评分: {news.get('sentiment_score', 0):.2f}
- 正面新闻比例: {news.get('positive_ratio', 0):.1%}
- 负面新闻比例: {news.get('negative_ratio', 0):.1%}
- 新闻数量: {news.get('news_count', 0)}条
- 新闻来源数: {news.get('source_count', 0)}个

💬 论坛/社媒情绪:
- 情绪评分: {forum.get('sentiment_score', 0):.2f}
- 讨论样本数: {forum.get('discussion_count', 0)}条
- 讨论热度: {forum.get('heat_level', '低热度')}
- 平台分布: {platform_breakdown_text}
- 热点主题: {', '.join(forum.get('hot_topics', [])) or '暂无'}
- 极端用语占比: {forum.get('extreme_ratio', 0.0):.1%}

📌 论坛/社媒标题示例:
{forum_titles_text}

📰 媒体覆盖度:
- 覆盖样本数: {media.get('coverage_count', 0)}条
- 覆盖来源数: {media.get('source_count', 0)}个

📌 样本标题示例:
{sample_titles_text}

💡 投资建议:
基于当前可获取的中国市场数据，建议投资者:
1. 优先参考多来源重复出现的关键信息
2. 将新闻情绪与财务数据、估值水平结合判断
3. 若样本数偏少，降低对短线情绪结论的权重
4. 关注公告、订单、中标、分红等高价值事件

⚠️ 数据说明:
本分析优先使用项目内缓存、AKShare/Tushare/BaoStock 可访问新闻源及公开财经新闻。
当论坛/社媒缓存缺失时，会尝试抓取东方财富股吧与雪球公开页面；若外站风控拦截，再降低该维度权重。

生成时间: {sentiment_data.get('timestamp', datetime.now().isoformat())}
"""

    except Exception as e:
        logger.error(f"[中文情绪] 报告生成失败: {ticker} - {e}", exc_info=True)
        return f"""
中国市场情绪分析 - {ticker}
分析日期: {curr_date}

❌ 分析失败: {str(e)}

💡 替代建议:
1. 查看财经新闻网站的相关报道
2. 关注公司公告和交易所披露信息
3. 参考专业机构的研究报告
4. 重点分析基本面和技术面数据

注: 中国市场情绪数据获取依赖外部源可用性，建议与其他分析维度交叉验证。
"""
