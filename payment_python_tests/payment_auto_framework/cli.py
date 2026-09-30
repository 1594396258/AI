from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ai_assistant import (
    analyze_failure,
    analyze_failure_with_ai,
    generate_contract_draft,
    review_contract_with_ai,
    save_contract_draft,
)
from .reporting import save_markdown_report


def main() -> None:
    parser = argparse.ArgumentParser(description="支付通道自动化框架 AI 辅助工具")
    sub = parser.add_subparsers(dest="command", required=True)
    draft = sub.add_parser("draft", help="从脱敏 JSON 样例生成通道配置初稿")
    draft.add_argument("samples", type=Path)
    draft.add_argument("--channel", required=True)
    draft.add_argument("--output", type=Path, required=True)
    draft.add_argument("--ai", action="store_true", help="使用显式配置的模型审查初稿")
    failure = sub.add_parser("analyze", help="分析证据 JSON")
    failure.add_argument("evidence", type=Path)
    failure.add_argument("--ai", action="store_true", help="使用显式配置的模型增强失败分析")
    report = sub.add_parser("report", help="从证据 JSON 生成 Markdown 报告")
    report.add_argument("evidence", type=Path)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "draft":
        samples = json.loads(args.samples.read_text(encoding="utf-8"))
        generated = generate_contract_draft(samples, channel=args.channel)
        save_contract_draft(generated, args.output)
        print(f"已生成配置初稿: {args.output}；签名和特殊状态必须人工审核")
        if args.ai:
            print(review_contract_with_ai(generated))
    elif args.command == "analyze":
        records = json.loads(args.evidence.read_text(encoding="utf-8"))
        result = analyze_failure(records)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.ai:
            print(analyze_failure_with_ai(records))
    else:
        records = json.loads(args.evidence.read_text(encoding="utf-8"))
        print(f"已生成报告: {save_markdown_report(records, args.output)}")


if __name__ == "__main__":
    main()
