# CCON BA: historical GitHub review audit (2026-10-27)

[Canonical JSON register](PR_REVIEW_COMMENT_REGISTER.json) has exact comment URLs, source paths, review thread IDs, severity, dispositions, linked fixes and remaining next actions for the **148 original historical findings**.

## Status after merged PR #102 and reviewed current-main findings

- **136 resolved / 12 open** of the original 148 findings, remaining all P2; historical P1 open = 0. **2** of the 12 open are marked outdated but still require source-level verification.
- The baseline before follow-up was 78 resolved / 70 open. **58 original findings** have been individually reviewed, replied to at their original comment and resolved during follow-up.
- PRs #94 through #103 (excluding no review-safe claims) have merged with all four synthetic GitHub Actions jobs successful. PR #104 is a standalone register reconciliation change.
- New AI-review threads in subsequent PRs are **not** members of the original 148 historical findings; original counts are unchanged.

## Remaining historical P2 by file

| Source file | Open findings |
|---|---:|
| `assets/dashboard.mjs` | 8 |
| `assets/dashboard.css` | 1 |
| `assets/queue-dom.mjs` | 1 |
| `docs/SQLITE_RETENTION_EVALUATION.md` | 1 |
| `weekly_workload.py` | 1 |

Remaining exact comments and thread IDs: [JSON register](PR_REVIEW_COMMENT_REGISTER.json). Fix confirmed bugs in separate scoped PRs with regression and green CI, reply to exact original thread and only then resolve it. Outdated status or adding comments does not prove implementation.

## Product backlog and human acceptance

The **129 canonical product requirements** remain independent: 40 code-IMPLEMENTED, 82 PARTIAL, 3 human GATE and 4 DEFERRED. **All 129 human_acceptance remain NOT_RECORDED**. The project is **BLOCKED_INDEPENDENT_UAT** under [Issue #50](https://github.com/slyvchenko/ccon-ba-task-tracker/issues/50). Independent BA gold cases in authorized private Jira/Kibana/CCON and Windows Chrome/Edge/NVDA/crash/8h acceptance and owner release decision are still outstanding. Synthetic CI cannot substitute for this acceptance, and GitHub merges do not update installed Windows clients. Never commit real corporate source data or credentials.
