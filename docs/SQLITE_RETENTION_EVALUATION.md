# SQLite tuning and private history retention: evaluation-only (v2.50.2)

## PERF-10: synthetic experiment, not production PRAGMA switch

Run `python sqlite_mode_study.py --tasks 100 --iterations 5`. The script creates **four independent temporary SQLite databases** with 100 synthetic tasks (25% synthetic `priority=High`): DELETE/WAL journal mode × with/without an expression index on `json_extract(snapshot,'$.priority')`. It reports query p95, SQLite query-plan index use, busy timeout and a successful `sqlite3.Connection.backup()` integrity check. The real BA database, installed journal mode, task data and production indexes are never read or modified. Only aggregate synthetic metrics are printed.

**Important:** the JSON filter is a candidate experiment, not proof that the existing production queue needs that index. A synthetic p95 is not a performance SLA; the effect of write contention, antivirus, Windows filesystem, snapshot size and real backup/restore must be assessed separately. No automatic WAL/index enablement was made. `PRAGMA synchronous=FULL` from v2.50.1 is retained.

## REL-09: safe read-only preview, no archive/delete

Run `python history_retention_preview.py --days 365` **only locally**, where your BA database is stored. The preview queries read-only SQLite and reports aggregate counts of history records older than the horizon, grouped by origin, excluding the **latest revision per task**. It does not include task IDs, notes, emails, history JSON, filenames or local paths. It does not archive/delete or update the main database, and preserves all import audit entries and historical revisions. Read-only SQLite connections on live WAL databases may still create or update the `-wal`/`-shm` sidecars; **do not claim this preview writes no files**. The counts are read from one SQLite snapshot.

No deletion or archive function is provided: the exact retention period, audit value, signed/encrypted archive destination, rescue/restore and explicit user approval are required before such a feature could be implemented. This avoids accidentally erasing useful user decisions.

## Open acceptance

Both PERF-10 and REL-09 remain **PARTIAL**. Windows/real-data benchmarks, storage pressure, restore drills, and human-approved retention policy are not proven by synthetic tests. No network transfer or background monitoring exists in these scripts. The 129-item backlog keeps `human_acceptance=NOT_RECORDED`.
