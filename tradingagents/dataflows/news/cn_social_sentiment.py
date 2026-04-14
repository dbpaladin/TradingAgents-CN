"""
中国股票社媒情绪抓取（轻量版）

目标：在未预置社媒缓存时，补充东方财富股吧/雪球公开页面的讨论样本，
用于情绪分析中的“讨论热度 + 标题倾向 + 极端用语”维度。
"""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Dict, List, Optional

import requests

from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 关键词用于估算情绪倾向，避免依赖外部NLP模型。
_BULLISH_WORDS = [
    "利好", "超预期", "看多", "看好", "买入", "增持", "反弹", "上涨", "突破", "稳了", "走强", "加仓",
]
_BEARISH_WORDS = [
    "利空", "看空", "卖出", "减持", "下跌", "暴跌", "崩", "雷", "快跑", "承压", "破位", "垃圾",
]
_EXTREME_WORDS = [
    "梭哈", "满仓", "all in", "清仓", "快跑", "垃圾", "必涨", "退市", "暴雷", "血亏", "无脑", "翻倍",
]


def _normalize_cn_symbol(raw_ticker: str) -> str:
    symbol = (raw_ticker or "").upper()
    for suffix in (".SH", ".SZ", ".SS", ".XSHG", ".XSHE", ".HK"):
        symbol = symbol.replace(suffix, "")
    return symbol.strip().zfill(6)[:6]


def _parse_datetime(text: Any) -> Optional[datetime]:
    if not text:
        return None
    if isinstance(text, datetime):
        return text
    value = str(text).strip()
    if not value:
        return None

    for candidate in (value.replace("Z", "+00:00"), value):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


def _extract_balanced_json_blob(text: str, marker: str) -> Optional[str]:
    idx = text.find(marker)
    if idx < 0:
        return None

    start = text.find("{", idx)
    if start < 0:
        return None

    depth = 0
    for pos in range(start, len(text)):
        char = text[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : pos + 1]
    return None


def _score_text_sentiment(text: str) -> float:
    content = (text or "").lower()
    if not content:
        return 0.0

    bull = sum(1 for word in _BULLISH_WORDS if word in content)
    bear = sum(1 for word in _BEARISH_WORDS if word in content)
    if bull + bear == 0:
        return 0.0
    return (bull - bear) / (bull + bear)


def _contains_extreme_words(text: str) -> bool:
    content = (text or "").lower()
    return any(word in content for word in _EXTREME_WORDS)


def fetch_eastmoney_guba_posts(ticker: str, max_posts: int = 40, timeout: int = 8) -> List[Dict[str, Any]]:
    """抓取东方财富股吧帖子列表。"""
    symbol = _normalize_cn_symbol(ticker)
    url = f"https://guba.eastmoney.com/list,{symbol}.html"
    headers = dict(_DEFAULT_HEADERS)
    headers["Referer"] = "https://guba.eastmoney.com/"

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        html = response.text

        blob = _extract_balanced_json_blob(html, "var article_list=")
        if not blob:
            logger.info(f"[社媒抓取] 股吧页面未找到文章列表: {symbol}")
            return []

        payload = json.loads(blob)
        rows = payload.get("re") or payload.get("data") or []

        results: List[Dict[str, Any]] = []
        for row in rows[: max(1, max_posts)]:
            title = str(row.get("post_title") or "").strip()
            if not title:
                continue

            post_id = str(row.get("post_id") or "").strip()
            publish_time = row.get("post_publish_time") or row.get("post_last_time")
            click_count = int(row.get("post_click_count") or 0)
            comment_count = int(row.get("post_comment_count") or 0)
            score = _score_text_sentiment(title)

            results.append(
                {
                    "symbol": symbol,
                    "platform": "eastmoney_guba",
                    "title": title,
                    "content": title,
                    "summary": title,
                    "source": "东方财富股吧",
                    "publish_time": publish_time,
                    "_sort_time": _parse_datetime(publish_time),
                    "url": f"https://guba.eastmoney.com/news,{symbol},{post_id}.html" if post_id else url,
                    "read_count": click_count,
                    "comment_count": comment_count,
                    "engagement": click_count + comment_count * 8,
                    "sentiment_score": score,
                    "sentiment": "positive" if score > 0.1 else ("negative" if score < -0.1 else "neutral"),
                    "extreme": _contains_extreme_words(title),
                    "type": "social",
                }
            )

        return results
    except Exception as e:
        logger.warning(f"[社媒抓取] 东方财富股吧抓取失败: {ticker} - {e}")
        return []


def fetch_xueqiu_posts(ticker: str, company_name: str = "", max_posts: int = 30, timeout: int = 8) -> List[Dict[str, Any]]:
    """
    轻量尝试抓取雪球帖子。

    说明：雪球存在 WAF 风控，公网环境经常返回挑战页；该函数失败时返回空列表，
    调用方应继续使用股吧/缓存数据，不中断主流程。
    """
    symbol = _normalize_cn_symbol(ticker)
    query = company_name.strip() or symbol
    url = "https://xueqiu.com/query/v1/search/status.json"
    params = {
        "sortId": "1",
        "q": query,
        "count": str(max(1, max_posts)),
        "page": "1",
    }
    headers = dict(_DEFAULT_HEADERS)
    headers["Referer"] = "https://xueqiu.com/"

    try:
        session = requests.Session()
        session.get("https://xueqiu.com", headers=headers, timeout=timeout)

        response = session.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        text = response.text

        # 风控拦截时通常返回 HTML 挑战页。
        if "<textarea id=\"renderData\"" in text or "aliyun_waf" in text:
            logger.info("[社媒抓取] 雪球触发风控，当前请求未返回结构化数据")
            return []

        payload = response.json()
        rows = payload.get("list") or payload.get("statuses") or payload.get("items") or []

        results: List[Dict[str, Any]] = []
        for row in rows[: max(1, max_posts)]:
            title = str(row.get("title") or row.get("text") or "").strip()
            if not title:
                continue

            created_at = row.get("created_at") or row.get("createdAt")
            score = _score_text_sentiment(title)

            results.append(
                {
                    "symbol": symbol,
                    "platform": "xueqiu",
                    "title": title,
                    "content": title,
                    "summary": title,
                    "source": "雪球",
                    "publish_time": created_at,
                    "_sort_time": _parse_datetime(created_at),
                    "url": str(row.get("target") or row.get("url") or "https://xueqiu.com"),
                    "read_count": int(row.get("view_count") or row.get("viewCount") or 0),
                    "comment_count": int(row.get("comment_count") or row.get("reply_count") or 0),
                    "engagement": int(row.get("fav_count") or 0) + int(row.get("retweet_count") or 0),
                    "sentiment_score": score,
                    "sentiment": "positive" if score > 0.1 else ("negative" if score < -0.1 else "neutral"),
                    "extreme": _contains_extreme_words(title),
                    "type": "social",
                }
            )

        return results
    except Exception as e:
        logger.warning(f"[社媒抓取] 雪球抓取失败: {ticker} - {e}")
        return []


def fetch_cn_social_posts(ticker: str, company_name: str = "", max_posts_per_source: int = 40) -> List[Dict[str, Any]]:
    """聚合抓取中国市场社媒帖子。"""
    guba_posts = fetch_eastmoney_guba_posts(ticker=ticker, max_posts=max_posts_per_source)
    xueqiu_posts = fetch_xueqiu_posts(
        ticker=ticker,
        company_name=company_name,
        max_posts=max(10, max_posts_per_source // 2),
    )

    posts = guba_posts + xueqiu_posts

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in posts:
        key = (
            re.sub(r"\s+", "", str(item.get("title", "")).lower())[:120],
            str(item.get("platform", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    deduped.sort(key=lambda row: row.get("_sort_time") or datetime.min, reverse=True)
    return deduped
