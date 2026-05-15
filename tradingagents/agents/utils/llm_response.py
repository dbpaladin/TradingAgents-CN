from __future__ import annotations

from typing import Any, Tuple


def extract_llm_response_text(response: Any) -> Tuple[str, str]:
    """Robustly extract visible text from heterogeneous LLM response shapes."""
    if response is None:
        return "", "none"

    content = getattr(response, "content", None)
    text = _normalize_content(content)
    if text:
        return text, "content"

    text_accessor = getattr(response, "text", None)
    if isinstance(text_accessor, str) and text_accessor.strip():
        return text_accessor.strip(), "text"
    if text_accessor is not None:
        text_value = str(text_accessor).strip()
        if text_value:
            return text_value, "text"

    content_blocks = getattr(response, "content_blocks", None)
    if content_blocks:
        block_text = _extract_from_blocks(content_blocks)
        if block_text:
            return block_text, "content_blocks"

    additional_kwargs = getattr(response, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        for key in ("text", "output_text", "reasoning_content", "reasoning"):
            value = additional_kwargs.get(key)
            normalized = _normalize_content(value)
            if normalized:
                return normalized, f"additional_kwargs.{key}"

    return "", "empty"


def _normalize_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                item_type = item.get("type")
                if item_type in {"text", "output_text"} and isinstance(item.get("text"), str):
                    parts.append(item["text"].strip())
                elif item_type == "reasoning" and isinstance(item.get("reasoning"), str):
                    parts.append(item["reasoning"].strip())
        return "\n".join(part for part in parts if part)
    return ""


def _extract_from_blocks(blocks: Any) -> str:
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in {"text", "output_text"} and isinstance(block.get("text"), str):
            text = block["text"].strip()
            if text:
                parts.append(text)
        elif block_type == "reasoning" and isinstance(block.get("reasoning"), str):
            text = block["reasoning"].strip()
            if text:
                parts.append(text)
    return "\n".join(parts)
