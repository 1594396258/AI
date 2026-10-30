---
name: tapd-testcase
description: Generate field-level Excel test cases from a TAPD story URL or TAPD requirement. Use when the user provides a tapd.cn story link, asks to write TAPD test cases, asks to generate testcase Excel, or says to use the TAPD testcase workflow/skill. Covers project background reading, TAPD API story retrieval, field/rule coverage extraction, and Excel output matching the local testcase template.
---

# TAPD Testcase

Use this skill to generate test case Excel files from TAPD requirements for the finance gateway project.

## Workflow

1. Parse the TAPD URL.
   - URL format: `https://www.tapd.cn/tapd_fe/{workspace_id}/story/detail/{full_story_id}`.
   - Use the full final story id. Do not truncate it.

2. Read local context before generating cases.
   - Project background: `D:/PyCharm 2025.2.3/myy1/AI/finance_project_overview/overview.md`.
   - Historical examples: read files under `D:/PyCharm 2025.2.3/myy1/AI/history_story/` to match naming, grouping, and coverage style.
   - Template workbook: `D:/PyCharm 2025.2.3/myy1/AI/testcase_template/testcase_template.xlsx`.

3. Fetch and clean the TAPD story.
   - Prefer `scripts/fetch_tapd_story.py`.
   - Authentication: Bearer token only. Do not use Basic Auth.
   - Token lookup order: `TAPD_ACCESS_TOKEN`, then the original Claude skill file at `C:/Users/hanquan.zeng/.claude/skills/tapd-testcase.md`.
   - If TAPD returns 403, report that the token is likely expired.
   - If TAPD returns empty data, re-check that the story id is the full id from the URL.

4. Build a coverage checklist before writing cases.
   - Extract all sections, pages, dialogs, interfaces, jobs, files, fields, statuses, permissions, and business rules.
   - For interface-like sections, cover request fields, response fields, examples, remarks, business rules, and abnormal branches.
   - For page/task/file requirements, cover UI filters, table columns, buttons, state transitions, validations, permissions, data isolation, file naming, file contents, schedules, time zones, retry/idempotency, and alerts.
   - Mark each checklist group as covered before final delivery.

5. Generate cases at field/rule granularity.
   - Each request parameter, response parameter, UI field, file column, summary field, status value, permission rule, validation rule, abnormal branch, and compatibility scenario should become at least one case.
   - Preserve original requirement details; do not collapse multiple independent validation points into one broad case.
   - Use names like `{模块}-{功能}：{字段/规则}描述`.
   - Group by requirement structure. Within a group, order cases as constraints, inputs/fields, outputs/display, abnormal scenarios, business rules.

6. Create the Excel workbook.
   - Use the local template columns and style where possible.
   - Required columns: 用例目录, 用例名称, 需求ID, 用例类型, 用例等级, 用例类别, 用例难易度, 前置条件, 用例步骤, 预期结果, 用例状态, 是否自动化, 创建人, 迭代, 功能标签, 备注.
   - `用例类型`: 功能用例.
   - `用例等级`: 高(冒烟用例) for P0/main flows, 中 for important fields/rules, 低 for boundaries/compatibility.
   - `用例类别`: 正向用例 or 反向用例.
   - Steps and expected results use `1、...\n2、...`.
   - Save under `D:/PyCharm 2025.2.3/myy1/outputs/tapd_{story_id}/` unless the user requests Desktop.

7. Verify before responding.
   - Inspect the workbook range/table and confirm row count.
   - Render a preview image and check that headers, wrapping, widths, and the demand id display are readable.
   - Scan for formula/cell errors if formulas are present.

## Output Expectations

Return the final `.xlsx` path/link and summarize the number of cases generated plus any meaningful verification notes.
