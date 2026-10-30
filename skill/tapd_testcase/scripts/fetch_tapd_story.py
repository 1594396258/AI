#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch and clean a TAPD story by URL.

Usage:
  python fetch_tapd_story.py <tapd_url> [output_dir]
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

CLAUDE_SKILL = Path(r"C:/Users/hanquan.zeng/.claude/skills/tapd-testcase.md")


def parse_tapd_url(url: str):
    patterns = [
        r"tapd\.cn/tapd_fe/(\d+)/story/detail/(\d+)",
        r"tapd\.cn/(\d+)/prong/stories/view/(\d+)",
        r"tapd\.cn/(\d+)/.*?/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)
    raise ValueError(f"Cannot parse TAPD URL: {url}")


def get_token():
    token = os.environ.get("TAPD_ACCESS_TOKEN", "").strip()
    if token:
        return token
    if CLAUDE_SKILL.exists():
        text = CLAUDE_SKILL.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"token\s*=\s*['\"]([A-Za-z0-9._-]{20,})['\"]", text)
        if match:
            return match.group(1)
        match = re.search(r"Bearer\s+([A-Za-z0-9._-]{20,})", text)
        if match:
            return match.group(1)
    raise RuntimeError("TAPD token not found. Set TAPD_ACCESS_TOKEN or update the Claude skill token.")


def clean_html(desc: str):
    desc = re.sub(r"<br\s*/?>", "\n", desc or "")
    desc = re.sub(r"<p[^>]*>", "\n", desc)
    desc = re.sub(r"<li[^>]*>", "\n- ", desc)
    desc = re.sub(r"<tr[^>]*>", "\n", desc)
    desc = re.sub(r"<td[^>]*>", " | ", desc)
    desc = re.sub(r"<th[^>]*>", " | ", desc)
    desc = re.sub(r"<[^>]+>", "", desc)
    replacements = {
        "&nbsp;": " ",
        "&gt;": ">",
        "&lt;": "<",
        "&amp;": "&",
        "&quot;": '"',
    }
    for old, new in replacements.items():
        desc = desc.replace(old, new)
    return re.sub(r"\n{3,}", "\n\n", desc).strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: fetch_tapd_story.py <tapd_url> [output_dir]", file=sys.stderr)
        return 2
    tapd_url = sys.argv[1]
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    workspace_id, story_id = parse_tapd_url(tapd_url)
    token = get_token()
    api_url = f"https://api.tapd.cn/stories?workspace_id={workspace_id}&id={story_id}"
    req = urllib.request.Request(api_url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError("TAPD API returned 403. The Bearer token is likely expired.") from exc
        raise

    if not data.get("data"):
        raise RuntimeError("TAPD API returned empty data. Check that story_id is the full id from the URL.")

    story = data["data"][0]["Story"]
    name = story.get("name", "")
    desc = clean_html(story.get("description", ""))
    out = output_dir / f"story_{story_id}_clean.txt"
    out.write_text(name + "\n\n" + desc, encoding="utf-8")
    print(json.dumps({"workspace_id": workspace_id, "story_id": story_id, "title": name, "path": str(out), "description_length": len(desc)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
