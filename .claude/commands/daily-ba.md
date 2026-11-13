---
description: Daily CCON BA analysis — sync Jira, analyse only new/changed tasks, import them
---

Run today's BA analysis for CCON BA Desk from this chat. Jira, Confluence and e-mail are
**read only**: never transition, comment, assign or send anything. Answer the user in Ukrainian.

Use the project's Python interpreter (on the analyst laptop:
`C:/Users/vslyvchenko/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`)
with `PYTHONUTF8=1`, from the app root. Elasticsearch/Kibana needs VPN or the office network.

1. **Sync.** `python jira_sync.py` (read-only GET). Stop and report if it fails.
2. **Worklist.** `python daily_delta.py list`. It returns only tasks that are NEW, CHANGED
   (Jira content changed; sprint moves/rank no longer count) or failing the QUALITY gate,
   active sprint first. If the list is empty, say so and stop. $ARGUMENTS may narrow it
   (e.g. `CCON-15600 CCON-15592` or `active` for the active sprint only).
3. **Analyse** each task, in batches of up to 9; with more than 9 tasks run batches in
   parallel forks, each writing its own `data/partial_analysis_<date>_<n>.json`:
   - `python daily_delta.py dump KEY ...` for description, all comments and the previous result;
   - `python daily_delta.py errors "exact error text"` for PROD counts (90/30/7 days, last flow)
     whenever the issue quotes a supplier/CCON error;
   - read linked issues' status and latest comments with `jira_sync.JiraClient.get` (GET only);
   - follow BA_ANALYSIS_RULES.md, TASK_DESCRIPTION_RULES.md and EMAIL_RULES.md; build each
     analysis with `analysis_kit.Kit().build(...)` (verbatim excerpts only, no invented facts;
     unread attachments are listed as UNAVAILABLE sources);
   - never print or copy passenger personal data, credentials or request headers.
4. **Check.** `python daily_delta.py check FILE` must exit 0 (every task fresh,
   STRUCTURALLY_VERIFIED, no diagnostics). Fix and re-check; a task that cannot pass
   (e.g. an epic with no text) is reported, not forced.
5. **Import.** Back up `ba_state.db`, `inbox/CCON_BA_Snapshot.json`, `data/questions`,
   `data/decisions` into `backups/before-daily-<date>/`, merge the batch files and run
   `python apply_analysis.py FILE --issues KEY1,KEY2,...`. Confirm `reportError` is null and
   there are no quality warnings, question or decision errors for the imported keys.
6. **Report** (Ukrainian, short): how many tasks analysed and why (new/changed/quality);
   the top items that need the analyst's decision or reply today, with the reason from the
   evidence; tasks that look closable; anything that could not be verified. Remind the user
   to refresh the page (Ctrl+F5). Drafts are drafts: nothing was sent.
