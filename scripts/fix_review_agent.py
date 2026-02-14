#!/usr/bin/env python3
"""
Agent that fixes code review comments from a GitHub PR.

Reads review comments (GitHub API JSON), uses an LLM to generate fixes per comment,
applies edits to the repo, and optionally commits and pushes.

Usage:
  python fix_review_agent.py --comments review-comments.json [--dry-run] [--no-push]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# TODO: add retry logic for API calls

def load_comments(path: str) -> list[dict]:
    """Load GitHub PR review comments from a JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        data = [data]
    return data


def get_comment_context(comment: dict) -> tuple[str, int, int | None, str, str]:
    """
    Extract from a GitHub comment: path, line, optional end_line, body, diff_hunk.
    """
    path = comment.get("path") or ""
    line = int(comment.get("line") or comment.get("original_line") or 0)
    start_line = comment.get("start_line")
    end_line = int(start_line) if start_line is not None else line
    body = (comment.get("body") or "").strip()
    diff_hunk = (comment.get("diff_hunk") or "").strip()
    return path, line, end_line if end_line != line else None, body, diff_hunk


def read_file_lines(file_path: str) -> list[str]:
    """Read file as list of lines (with newlines preserved)."""
    path = Path(file_path)
    if not path.is_file():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return f.readlines()


def write_file_lines(file_path: str, lines: list[str]) -> None:
    """Write lines to file (lines should include newlines where desired)."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)


def extract_line_range(lines: list[str], start: int, end: int | None) -> str:
    """1-based start/end inclusive. Returns concatenated line content."""
    if not lines:
        return ""
    end = end or start
    start = max(1, min(start, len(lines)))
    end = max(start, min(end, len(lines)))
    return "".join(lines[start - 1 : end])


def apply_replacement_by_lines(
    file_path: str, start_line: int, end_line: int | None, new_content: str
) -> bool:
    """Replace lines start_line..end_line (1-based) with new_content. Returns True if changed."""
    lines = read_file_lines(file_path)
    if not lines:
        return False
    end_line = end_line or start_line
    start_line = max(1, min(start_line, len(lines)))
    end_line = max(start_line, min(end_line, len(lines)))
    replacement_lines = new_content.splitlines(keepends=True)
    if replacement_lines and not replacement_lines[-1].endswith("\n"):
        replacement_lines[-1] += "\n"
    elif not replacement_lines:
        replacement_lines = ["\n"]
    new_lines = lines[: start_line - 1] + replacement_lines + lines[end_line:]
    new_content_full = "".join(new_lines)
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write(new_content_full)
    return True


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def call_llm_for_fix(
    file_path: str,
    line_content: str,
    comment_body: str,
    diff_hunk: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: str | None = None,
) -> str | None:
    """
    Ask the LLM for a replacement for the given line content.
    Returns the new fragment to use, or None if no fix could be generated.
    Supports OpenAI and OpenRouter (set base_url to OPENROUTER_BASE_URL).
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("openai package required. pip install openai", file=sys.stderr)
        return None

    client = OpenAI(api_key=api_key, base_url=base_url)
    prompt = f"""You are a code review fix agent. A reviewer left a comment on this code. Your job is to return ONLY the fixed code that should replace the given snippet—no explanation, no markdown, no quotes.

File: {file_path}

Code snippet (exact lines from the file):
```
{line_content}
```

Reviewer comment:
{comment_body}
"""
    if diff_hunk:
        prompt += f"""

Diff context (for reference):
```
{diff_hunk}
```
"""

    prompt += """
Return ONLY the replacement code (the fixed lines). Preserve indentation and style. Do not include the triple backticks or any commentary. If no change is needed, return the exact same snippet.
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You output only the replacement code, nothing else. No markdown, no explanation."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    text = (response.choices[0].message.content or "").strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text if text else None


def process_comments(
    comments: list[dict],
    repo_root: str,
    api_key: str,
    dry_run: bool = False,
    model: str = "gpt-4o-mini",
    base_url: str | None = None,
) -> int:
    """
    Process each comment: fetch context, call LLM, apply fix.
    Returns the number of comments that led to an applied fix.
    """
    repo_root_path = Path(repo_root).resolve()
    applied = 0

    for i, comment in enumerate(comments):
        path, line, end_line, body, diff_hunk = get_comment_context(comment)
        if not path or not body:
            continue

        file_path = repo_root_path / path
        if not file_path.is_file():
            print(f"[{i+1}] Skip: file not found {path}", file=sys.stderr)
            continue

        lines = read_file_lines(str(file_path))
        start_line = int(comment.get("start_line") or line)
        end_line_use = int(comment.get("line") or line)
        if start_line > end_line_use:
            start_line, end_line_use = end_line_use, start_line
        snippet = extract_line_range(lines, start_line, end_line_use)
        if not snippet.strip():
            print(f"[{i+1}] Skip: no content at {path}:{line}", file=sys.stderr)
            continue

        print(f"[{i+1}] {path}:{start_line}-{end_line_use} — \"{body[:60]}...\"" if len(body) > 60 else f"[{i+1}] {path}:{start_line}-{end_line_use} — \"{body}\"", file=sys.stderr)

        new_fragment = call_llm_for_fix(
            path, snippet, body, diff_hunk, api_key, model=model, base_url=base_url
        )
        if not new_fragment:
            continue

        if dry_run:
            print(f"  [dry-run] Would replace with:\n{new_fragment[:200]}...\n" if len(new_fragment) > 200 else f"  [dry-run] Would replace with:\n{new_fragment}\n", file=sys.stderr)
            applied += 1
            continue

        if apply_replacement_by_lines(str(file_path), start_line, end_line_use, new_fragment):
            applied += 1
            print(f"  Applied.", file=sys.stderr)
        else:
            print(f"  Failed to apply (content mismatch).", file=sys.stderr)

    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix code review comments using an LLM.")
    parser.add_argument("--comments", required=True, help="Path to JSON file with GitHub PR review comments")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Print proposed fixes without editing files")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model ID (default: gpt-4o-mini; use e.g. openai/gpt-4o-mini for OpenRouter)")
    args = parser.parse_args()

    # Prefer OpenRouter if OPENROUTER_API_KEY is set; otherwise use OPENAI_API_KEY
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = OPENROUTER_BASE_URL if os.environ.get("OPENROUTER_API_KEY") else None

    if not api_key:
        print("Set OPENAI_API_KEY or OPENROUTER_API_KEY.", file=sys.stderr)
        return 1

    comments = load_comments(args.comments)
    if not comments:
        print("No comments to process.", file=sys.stderr)
        return 0

    applied = process_comments(
        comments,
        args.repo_root,
        api_key,
        dry_run=args.dry_run,
        model=args.model,
        base_url=base_url,
    )
    print(f"Processed {len(comments)} comment(s), applied {applied} fix(es).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
