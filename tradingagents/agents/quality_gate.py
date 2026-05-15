from typing import Dict, List, Tuple

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


def create_quality_gate():
    """Create a lightweight quality-gate node for analyst reports."""

    def quality_gate_node(state) -> Dict[str, str]:
        gate_config = state.get("quality_gate_config", {}) or {}
        if not gate_config.get("enabled", True):
            return {"data_quality_summary": "## Data Quality Summary\n- Status: disabled\n"}

        min_report_chars = int(gate_config.get("min_report_chars", 120))
        max_issues_in_summary = int(gate_config.get("max_issues_in_summary", 6))
        hard_fail_threshold = int(gate_config.get("hard_fail_threshold", 3))

        selected_analysts = state.get("selected_analysts", []) or []
        analyst_to_report: Dict[str, Tuple[str, str]] = {
            "market": ("market_report", "市场分析"),
            "emotion": ("a_share_sentiment_report", "A股情绪"),
            "fund_flow": ("fund_flow_report", "资金流向"),
            "theme_rotation": ("theme_rotation_report", "题材轮动"),
            "institutional_theme": ("institutional_theme_report", "机构布局"),
            "social": ("sentiment_report", "社媒情绪"),
            "news": ("news_report", "新闻分析"),
            "fundamentals": ("fundamentals_report", "基本面"),
        }
        active_reports: List[Tuple[str, str]] = [
            analyst_to_report[a] for a in selected_analysts if a in analyst_to_report
        ]
        if not active_reports:
            active_reports = [("market_report", "市场分析")]

        issues: List[str] = []
        good_count = 0
        hard_fail_count = 0
        degraded_markers = ("获取失败", "降级", "为空", "error", "failed")

        for key, label in active_reports:
            value = state.get(key, "")
            text = value if isinstance(value, str) else str(value or "")
            stripped = text.strip()

            if not stripped:
                issues.append(f"{label}: 空内容")
                hard_fail_count += 1
                continue

            if any(marker in stripped.lower() for marker in degraded_markers):
                issues.append(f"{label}: 疑似降级内容")
                hard_fail_count += 1
                continue

            if len(stripped) < min_report_chars:
                issues.append(f"{label}: 内容过短({len(stripped)} chars)")
                continue

            good_count += 1

        total = len(active_reports)
        if good_count >= 7:
            grade = "A"
        elif good_count >= 6:
            grade = "B"
        elif good_count >= 5:
            grade = "C"
        else:
            grade = "D"
        if total <= 4:
            if good_count == total:
                grade = "A"
            elif good_count >= max(total - 1, 1):
                grade = "B"
            elif good_count >= max(total - 2, 1):
                grade = "C"
            else:
                grade = "D"

        red_flag = hard_fail_count >= hard_fail_threshold
        issue_summary = "；".join(issues[:max_issues_in_summary]) if issues else "无明显问题"
        summary = (
            f"## Data Quality Summary\n"
            f"- Grade: {grade}\n"
            f"- Passed: {good_count}/{total}\n"
            f"- HardFail: {hard_fail_count}\n"
            f"- RedFlag: {'YES' if red_flag else 'NO'}\n"
            f"- Issues: {issue_summary}\n"
        )

        logger.info(
            "[Quality Gate] grade=%s passed=%s/%s hard_fail=%s red_flag=%s issues=%s",
            grade,
            good_count,
            total,
            hard_fail_count,
            red_flag,
            len(issues),
        )
        return {"data_quality_summary": summary}

    return quality_gate_node
