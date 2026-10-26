# v2.45 local backup creation timestamp integrity

A verified SQLite backup must match three independent signals: SHA256, SQLite integrity/schema, and UTC creation identity. New metadata validation compares the `backup-YYYYMMDDTHHMMSSZ-*.sqlite3` filename timestamp with the manifest `createdAt` (within one second for subsecond precision), rejects missing/naive/mismatched dates, and ensures unexpected future timestamps don't suppress fresh automatic backups after the system clock moves backward.

This is deliberately a **fail-closed verification change**, not a backup format migration. Existing backup files created by the application remain valid because their filename and manifest originate from the same UTC timestamp. Invalid metadata is ignored for freshness decisions; old verified copies are never automatically deleted due this check.

Synthetic tests cover ordinary restore status, invalid date, naive timestamp, far-future forged metadata and a three-hour host-clock rollback. SQL payloads and personal Jira data do not enter CLI output, tests or GitHub.

## Windows-only verification remains OPEN

Test local time corrections including DST, OS sync rollback, Windows Task Scheduler duplicate instance, interrupted backup, BitLocker/ACL, rescue copy and lost-power recovery using a synthetic or company-approved test instance. Verify backups are accessible only to the intended user. CI on Linux cannot assert Windows ACLs, file locking or true power-loss behavior.

Only restore with the **offline** CLI, after stopping all clients, and after verifying actual contents/revision. No silent recovery or automatic restore was added.
