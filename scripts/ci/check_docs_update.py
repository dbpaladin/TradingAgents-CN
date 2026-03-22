#!/usr/bin/env python3
"""Lightweight guardrail for code changes that should ship with docs updates."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


DOC_PATTERNS = [
    "README.md",
    "*/README.md",
    "docs/**",
    "*.md",
    "*.rst",
    "*.adoc",
]

IGNORE_PATTERNS = [
    ".github/workflows/**",
    "assets/**",
    "history_chat/**",
    "images/**",
    "logs/**",
    "reports/**",
    "results/**",
    "tests/**",
    "**/__pycache__/**",
    "**/*.lock",
    "frontend/yarn.lock",
    "uv.lock",
]


@dataclass(frozen=True)
class Rule:
    name: str
    code_patterns: tuple[str, ...]
    doc_targets: tuple[str, ...]


RULES = [
    Rule(
        name="backend",
        code_patterns=("app/**", "tradingagents/**", "cli/**", "main.py"),
        doc_targets=(
            "README.md",
            "docs/README.md",
            "docs/features/**",
            "docs/fixes/**",
            "docs/guides/**",
            "docs/releases/CHANGELOG.md",
            "docs/usage/**",
        ),
    ),
    Rule(
        name="frontend",
        code_patterns=("frontend/**", "web/**"),
        doc_targets=(
            "README.md",
            "docs/README.md",
            "docs/frontend/**",
            "docs/features/**",
            "docs/guides/**",
            "docs/releases/CHANGELOG.md",
            "docs/usage/**",
        ),
    ),
    Rule(
        name="deployment",
        code_patterns=(
            "docker/**",
            "nginx/**",
            "docker-compose*.yml",
            "Dockerfile*",
            "scripts/startup/**",
            "scripts/*service*.sh",
            "scripts/*service*.py",
            "scripts/*service*.ps1",
        ),
        doc_targets=(
            "README.md",
            "docs/README.md",
            "docs/deployment/**",
            "docs/docker/**",
            "docs/guides/docker-deployment-guide.md",
            "docs/releases/CHANGELOG.md",
        ),
    ),
    Rule(
        name="configuration",
        code_patterns=("config/**", ".env.example", "app/core/**", "app/services/config_*.py"),
        doc_targets=(
            "README.md",
            "config/README.md",
            "docs/README.md",
            "docs/configuration/**",
            "docs/guides/config-management-guide.md",
            "docs/releases/CHANGELOG.md",
        ),
    ),
]


def run_git_diff(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def classify_files(files: list[str]) -> tuple[list[str], list[str]]:
    docs = [path for path in files if matches_any(path, DOC_PATTERNS)]
    code = [
        path
        for path in files
        if not matches_any(path, DOC_PATTERNS) and not matches_any(path, IGNORE_PATTERNS)
    ]
    return docs, code


def find_triggered_rules(code_files: list[str]) -> list[Rule]:
    triggered = []
    for rule in RULES:
        if any(matches_any(path, rule.code_patterns) for path in code_files):
            triggered.append(rule)
    return triggered


def format_paths(paths: Iterable[str]) -> str:
    return "\n".join(f"  - {path}" for path in paths)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail when sensitive code changes are missing accompanying docs updates."
    )
    parser.add_argument("--base", default="HEAD~1", help="Base git ref")
    parser.add_argument("--head", default="HEAD", help="Head git ref")
    args = parser.parse_args()

    changed_files = run_git_diff(args.base, args.head)
    if not changed_files:
        print("No changed files detected.")
        return 0

    doc_files, code_files = classify_files(changed_files)
    triggered_rules = find_triggered_rules(code_files)

    if not code_files or not triggered_rules:
        print("No sensitive code changes detected that require documentation review.")
        return 0

    if doc_files:
        print("Documentation update detected alongside sensitive code changes.")
        print("Changed docs:")
        print(format_paths(doc_files))
        return 0

    print("Documentation check failed.")
    print()
    print("Sensitive code changes were detected without any matching docs update.")
    print("Changed code files:")
    print(format_paths(code_files[:20]))
    if len(code_files) > 20:
        print(f"  - ... {len(code_files) - 20} more")
    print()
    print("Suggested documentation targets:")
    suggestions = []
    for rule in triggered_rules:
        for target in rule.doc_targets:
            if target not in suggestions:
                suggestions.append(target)
    print(format_paths(suggestions))
    print()
    print(
        "If this change truly does not affect users, operators, deployment, or configuration, "
        "add a short note to docs/releases/CHANGELOG.md or another relevant docs file."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
