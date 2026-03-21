from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from tradingagents.utils.logging_init import get_logger

logger = get_logger("agents.prompt_context")


def _normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in str(text or "").splitlines()).strip()


def _take_priority_lines(lines: Iterable[str], max_chars: int) -> str:
    chosen: List[str] = []
    total = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if not (
            line.startswith("#")
            or line.startswith("-")
            or line.startswith("*")
            or line.startswith("**")
            or "结论" in line
            or "建议" in line
            or "风险" in line
            or "目标" in line
            or "阶段" in line
            or "主线" in line
            or "摘要" in line
        ):
            continue

        addition = len(line) + (1 if chosen else 0)
        if total + addition > max_chars:
            break
        chosen.append(line)
        total += addition

    return "\n".join(chosen)


def compact_text(text: str, max_chars: int, label: str = "") -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""

    if len(normalized) <= max_chars:
        return normalized

    priority = _take_priority_lines(normalized.splitlines(), max_chars=max_chars)
    if len(priority) >= max_chars * 0.6:
        compacted = priority[:max_chars].rstrip()
    else:
        head_budget = max_chars // 2
        tail_budget = max_chars - head_budget - 20
        compacted = (
            normalized[:head_budget].rstrip()
            + "\n...\n[中间内容已压缩]\n...\n"
            + normalized[-tail_budget:].lstrip()
        )

    if label:
        logger.info(
            f"🗜️ [上下文压缩] {label}: {len(normalized)} -> {len(compacted)} 字符"
        )
    return compacted


def compact_history(text: str, max_chars: int, label: str = "") -> str:
    normalized = _normalize_text(text)
    if not normalized or len(normalized) <= max_chars:
        return normalized

    compacted = normalized[-max_chars:]
    split_idx = compacted.find("\n")
    if split_idx != -1 and split_idx < max_chars // 3:
        compacted = compacted[split_idx + 1 :]

    compacted = "[仅保留最近对话]\n" + compacted.strip()
    if label:
        logger.info(
            f"🗜️ [历史压缩] {label}: {len(normalized)} -> {len(compacted)} 字符"
        )
    return compacted


def format_memories(memories: Optional[List[Dict]], max_chars: int, label: str = "") -> str:
    if not memories:
        return ""

    chunks: List[str] = []
    for rec in memories:
        recommendation = str(rec.get("recommendation", "")).strip()
        if recommendation:
            chunks.append(recommendation)

    joined = "\n\n".join(chunks)
    return compact_text(joined, max_chars=max_chars, label=label)
