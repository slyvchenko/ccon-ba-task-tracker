# M1 — Inbox to OneDrive

Purpose: copy selected inbound mail into a OneDrive drop folder for ingestion.

## Suggested flow
1. Trigger on new inbox message.
2. Filter by sender/domain/subject rules.
3. Build a deterministic filename.
4. Save body and metadata.
5. Save attachments when relevant.
6. Let the local tracker link the message to a case/task.
