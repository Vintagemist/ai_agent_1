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
from collections import defaultdict

# TODO: add retry logic for API calls


def group_comments_by_file(comments: list[dict]) -> dict[str, list[dict]]:
    """Group comments by file path for batch processing."""
    grouped = defaultdict(list)
    for comment in comments:
        path = comment.get("path")
        if path:
            grouped[path].append(comment)
    return dict(grouped)

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


def call_llm_for_batch_fix(
    file_path: str,
    file_lines: list[str],
    comments: list[dict],
    api_key: str,
    model: str = "claude-opus-4-6",
) -> list[dict]:
    """
    Process multiple comments for a single file in one LLM call.
    Returns a list of fixes with structure:
    [
      {
        "comment_index": int,
        "line_start": int,
        "line_end": int,
        "fixed_code": str,
        "confidence": str,
        "explanation": str
      },
      ...
    ]
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print("anthropic package required. pip install anthropic", file=sys.stderr)
        return []

    client = Anthropic(api_key=api_key)

    # Build consolidated prompt
    file_content = "".join(file_lines)
    prompt = f"""You are fixing multiple code review comments for this file.

File: {file_path}

Full file content:
```
{file_content}
```

Review comments to address:
"""

    for i, comment in enumerate(comments, 1):
        line = comment.get("line") or comment.get("original_line")
        start_line = comment.get("start_line") or line
        body = comment.get("body", "").strip()
        prompt += f"\n{i}. Lines {start_line}-{line}: {body}"
        diff_hunk = comment.get("diff_hunk", "").strip()
        if diff_hunk:
            prompt += f"\n   Diff context:\n   ```\n   {diff_hunk}\n   ```"

    prompt += """

Return a JSON array of fixes:
[
  {
    "comment_index": <number>,
    "line_start": <number>,
    "line_end": <number>,
    "fixed_code": "<replacement code>",
    "confidence": "high|medium|low",
    "explanation": "<brief description>"
  },
  ...
]

Rules:
- Return ONLY the JSON array, no markdown fences or extra text
- Preserve exact indentation and coding style
- comment_index corresponds to the numbered comments above
- If a comment doesn't require changes, omit it from the array
- Use "high" confidence for clear fixes, "medium" for reasonable fixes, "low" for uncertain fixes"""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=8192,  # Higher limit for batch processing
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if text.startswith("```json"):
            text = text[7:]  # Remove ```json
        elif text.startswith("```"):
            text = text[3:]  # Remove ```
        if text.endswith("```"):
            text = text[:-3]  # Remove closing ```
        text = text.strip()

        # Parse JSON response
        fixes = json.loads(text)

        if not isinstance(fixes, list):
            print(f"  Expected JSON array, got {type(fixes)}", file=sys.stderr)
            return []

        return fixes

    except json.JSONDecodeError as e:
        print(f"  Error parsing JSON response: {e}", file=sys.stderr)
        print(f"  Raw response: {text[:200]}...", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  Error calling Claude API: {e}", file=sys.stderr)
        return []


def call_llm_for_fix(
    file_path: str,
    line_content: str,
    comment_body: str,
    diff_hunk: str,
    api_key: str,
    model: str = "claude-opus-4-6",
) -> tuple[str | None, str]:
    """
    Ask Claude for a replacement for the given line content.
    Returns (new_fragment, confidence) or (None, "") if no fix could be generated.

    Confidence levels: "high", "medium", "low"
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print("anthropic package required. pip install anthropic", file=sys.stderr)
        return None, ""

    client = Anthropic(api_key=api_key)

    prompt = f"""You are a code review fix agent. A reviewer left a comment on this code.

File: {file_path}

Code snippet (exact lines from the file):
```
{line_content}
```

Reviewer comment:
{comment_body}"""

    if diff_hunk:
        prompt += f"""

Diff context (for reference):
```
{diff_hunk}
```"""

    prompt += """

Provide your response in JSON format:
{
  "fixed_code": "the replacement code (preserve exact indentation and style)",
  "confidence": "high|medium|low",
  "explanation": "brief description of what changed"
}

Rules:
- Return ONLY the JSON object, no markdown fences or extra text
- Preserve exact indentation and coding style
- If no change is needed, return the original code with confidence "low"
- Use "high" confidence for clear, unambiguous fixes
- Use "medium" confidence for reasonable fixes that might need review
- Use "low" confidence for unclear or speculative fixes"""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0.2,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if text.startswith("```json"):
            text = text[7:]  # Remove ```json
        elif text.startswith("```"):
            text = text[3:]  # Remove ```
        if text.endswith("```"):
            text = text[:-3]  # Remove closing ```
        text = text.strip()

        # Parse JSON response
        result = json.loads(text)

        fixed_code = result.get("fixed_code", "").strip()
        confidence = result.get("confidence", "low").lower()
        explanation = result.get("explanation", "")

        if explanation:
            print(f"  Explanation: {explanation}", file=sys.stderr)

        # Validate confidence level
        if confidence not in ["high", "medium", "low"]:
            confidence = "low"

        return fixed_code if fixed_code else None, confidence

    except json.JSONDecodeError as e:
        print(f"  Error parsing JSON response: {e}", file=sys.stderr)
        print(f"  Raw response: {text[:200]}...", file=sys.stderr)
        return None, ""
    except Exception as e:
        print(f"  Error calling Claude API: {e}", file=sys.stderr)
        return None, ""


def process_comments(
    comments: list[dict],
    repo_root: str,
    api_key: str,
    dry_run: bool = False,
    model: str = "claude-opus-4-6",
    min_confidence: str = "medium",
) -> int:
    """
    Process each comment: fetch context, call LLM, apply fix.
    Returns the number of comments that led to an applied fix.

    min_confidence: Only apply fixes with this confidence level or higher.
                   Options: "low", "medium", "high"
    """
    repo_root_path = Path(repo_root).resolve()
    applied = 0

    # Confidence level mapping for comparison
    confidence_levels = {"low": 0, "medium": 1, "high": 2}
    min_confidence_value = confidence_levels.get(min_confidence.lower(), 1)

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

        new_fragment, confidence = call_llm_for_fix(
            path, snippet, body, diff_hunk, api_key, model=model
        )

        if not new_fragment:
            print(f"  No fix generated", file=sys.stderr)
            continue

        # Filter by confidence threshold
        confidence_value = confidence_levels.get(confidence.lower(), 0)
        if confidence_value < min_confidence_value:
            print(f"  Skipped (confidence: {confidence}, required: {min_confidence})", file=sys.stderr)
            continue

        print(f"  Confidence: {confidence}", file=sys.stderr)

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


def process_comments_batch(
    comments: list[dict],
    repo_root: str,
    api_key: str,
    dry_run: bool = False,
    model: str = "claude-opus-4-6",
    min_confidence: str = "medium",
) -> int:
    """
    Process comments using batch mode - group by file and process multiple comments per file.
    Returns the number of comments that led to an applied fix.
    """
    repo_root_path = Path(repo_root).resolve()
    applied = 0

    # Confidence level mapping for comparison
    confidence_levels = {"low": 0, "medium": 1, "high": 2}
    min_confidence_value = confidence_levels.get(min_confidence.lower(), 1)

    # Group comments by file
    grouped = group_comments_by_file(comments)

    for file_path_str, file_comments in grouped.items():
        file_path = repo_root_path / file_path_str

        if not file_path.is_file():
            print(f"Skip: file not found {file_path_str} ({len(file_comments)} comments)", file=sys.stderr)
            continue

        print(f"\n=== Processing {file_path_str} ({len(file_comments)} comment(s)) ===", file=sys.stderr)

        # Read file once for all comments
        file_lines = read_file_lines(str(file_path))
        if not file_lines:
            print(f"  Skip: could not read file", file=sys.stderr)
            continue

        # Process all comments for this file in one LLM call
        fixes = call_llm_for_batch_fix(
            file_path_str, file_lines, file_comments, api_key, model=model
        )

        if not fixes:
            print(f"  No fixes generated", file=sys.stderr)
            continue

        # Apply fixes
        for fix in fixes:
            comment_idx = fix.get("comment_index", 0)
            line_start = fix.get("line_start", 0)
            line_end = fix.get("line_end", line_start)
            fixed_code = fix.get("fixed_code", "")
            confidence = fix.get("confidence", "low").lower()
            explanation = fix.get("explanation", "")

            # Validate confidence level
            if confidence not in ["high", "medium", "low"]:
                confidence = "low"

            # Filter by confidence threshold
            confidence_value = confidence_levels.get(confidence, 0)
            if confidence_value < min_confidence_value:
                print(f"  [{comment_idx}] Skipped (confidence: {confidence}, required: {min_confidence})", file=sys.stderr)
                continue

            print(f"  [{comment_idx}] Lines {line_start}-{line_end} | Confidence: {confidence}", file=sys.stderr)
            if explanation:
                print(f"      {explanation}", file=sys.stderr)

            if dry_run:
                print(f"      [dry-run] Would replace with:\n{fixed_code[:150]}...\n" if len(fixed_code) > 150 else f"      [dry-run] Would replace with:\n{fixed_code}\n", file=sys.stderr)
                applied += 1
                continue

            if apply_replacement_by_lines(str(file_path), line_start, line_end, fixed_code):
                applied += 1
                print(f"      Applied.", file=sys.stderr)
                # Re-read file after each change for subsequent changes
                file_lines = read_file_lines(str(file_path))
            else:
                print(f"      Failed to apply.", file=sys.stderr)

    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix code review comments using Claude AI.")
    parser.add_argument("--comments", required=True, help="Path to JSON file with GitHub PR review comments")
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="Print proposed fixes without editing files")
    parser.add_argument("--model", default="claude-opus-4-6", help="Claude model ID (default: claude-opus-4-6)")
    parser.add_argument("--min-confidence", default="medium", choices=["low", "medium", "high"],
                       help="Minimum confidence level to apply fixes (default: medium)")
    parser.add_argument("--batch", action="store_true",
                       help="Use batch mode (process multiple comments per file in one LLM call)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        print("Set ANTHROPIC_API_KEY environment variable.", file=sys.stderr)
        return 1

    comments = load_comments(args.comments)
    if not comments:
        print("No comments to process.", file=sys.stderr)
        return 0

    if args.batch:
        print(f"Using batch mode", file=sys.stderr)
        applied = process_comments_batch(
            comments,
            args.repo_root,
            api_key,
            dry_run=args.dry_run,
            model=args.model,
            min_confidence=args.min_confidence,
        )
    else:
        print(f"Using single-comment mode", file=sys.stderr)
        applied = process_comments(
            comments,
            args.repo_root,
            api_key,
            dry_run=args.dry_run,
            model=args.model,
            min_confidence=args.min_confidence,
        )

    print(f"\nProcessed {len(comments)} comment(s), applied {applied} fix(es).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
