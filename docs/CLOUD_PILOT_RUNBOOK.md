# CCON BA Desk v2.6: private single-user cloud pilot

**Status:** Container source and tests implemented; NOT deployed to a live cloud.
**Scope:** only the configured analyst's assigned CCON Jira issues, active sprint first.
**Integration policy:** Jira read-only; no Confluence changes; emails copied for manual use.

## Delivered code

- Explicit analyst account ID required in cloud mode; no service-account
  `currentUser()` ambiguity.
- Active sprint from one configured Jira Software board. Scores 0–100
  from five validated factors (25/25/20/20/10).
- Opt-in, approved HTTPS Chat Completions-compatible model adapter,
  evidence-backed dossiers, requirements, QA cases, questions and drafts.
- Context, manual-note and prompt-version-aware analysis reuse.
- Daily single-worker scheduler after 08:00 Europe/Warsaw; successful
  receipt persisted only after full import; retry failed run later.
- Caddy HTTPS -> Nginx auth_request -> oauth2-proxy OIDC -> private
  Python app. All HTML/API/file endpoints also validate trusted proxy
  shared secret and the exact single approved user email.
- No backend, auth server or worker port published to the host.
- Persistent SQLite Docker volume for one analyst. Not multi-user HA.

## Deployment prerequisites

1. Company security/data/AI processing approval: Jira, supplier logs,
   email, retention, model processing and cloud region.
2. Approved cloud host/VM with Docker Compose, public DNS, firewall,
   encrypted persistent disk and tested encrypted off-host backup.
3. Company OIDC SSO application: issuer, client ID/secret, exact
   callback `https://YOUR_DOMAIN/oauth2/callback` and single user access.
4. Read-only Jira credentials, **the analyst's own account ID**, and
   CCON board ID. Do not use the service account as the analyst.
5. Company-approved Chat Completions-compatible endpoint/model with
   JSON-object responses; provider key and explicit company-data consent.
6. Review at least 20 real Jira analyses before production reliance.

The coding environment lacks the corporate cloud account, DNS, OIDC,
Jira runtime credentials, an approved model key and company permissions.
Therefore no public service or working login URL has been claimed.

## Steps for an approved administrator

- Verify whether corporate policy allows use of the currently public
  GitHub repository. Never commit Jira snapshots, tokens, PNRs, logs,
  emails, staff/customer data or real `.env` values.
- Review and merge dependent PRs in order; copy `.env.example` to `.env`
  on the trusted host; configure all placeholders and restrictive file ACL.
- Set a long cryptographically random proxy shared secret and 32-byte
  random OAuth2 cookie secret. Store sensitive values in secrets manager
  for production rather than in deployment files.
- Validate and build the private pilot:

```sh
docker compose --env-file .env config -q
docker compose --env-file .env build
docker compose --env-file .env up -d
docker compose --env-file .env ps
```

- Verify only Caddy is reachable at public ports 80/443. The app
  listens on Docker's private port 8765 only. Confirm that anonymous,
  other-user, forged-header and cross-origin requests fail.
- Keep `CCON_ALLOW_CORPORATE_AI_UPLOAD=NO` until corporate data-sharing
  approval is explicit. Set `YES` only for the configured approved host.
  Jira task data and personal notes are transmitted to that model.
- Test `cloud_scheduler.py --once` on the worker with an authorized
  provider and check `data/last_daily_success.json` in the runtime volume.
  This is a supervised operational smoke test, not a CI-only claim.
- Confirm Jira query selects the user, not the API principal; test
  one sprint, one backlog, one left-scope, and one Jira Done case.
- Restart app and worker; confirm stored notes, drafts and history persist.

## Security and operational constraints

**No exposed local server.** Never publish port 8765 or run the old
localhost HTTP entrypoint with public bind. OIDC identity is verified
by oauth2-proxy/Nginx; backend independently requires an injected
internal shared secret and exact verified email.

**Provider approval.** The AI adapter accepts only HTTPS endpoint with
the explicitly allowlisted hostname and compatible chat completions API.
If source JSON is too large, analysis fails instead of silently
truncating the evidence. Unread ZIP/PDF/email sources stay unknown.

**Data persistence.** Docker named volumes survive normal redeploys
but are not intrinsically encrypted or backed up. Use encrypted cloud
storage, ACLs, restricted administrators, retention and off-host restore
tests. Pilot SQLite is single-writer, not a multi-user production DB.

**Prompt evolution.** Automated daily changes are restricted to the
approved diagnostic checklist. Core BA rules require PR reviews,
regression tests and human A/B evaluation before promotion.

**No write-back.** No Jira/Confluence mutations or outgoing supplier
emails. User-owned status and notes are stored only in the BA Desk DB.
Browser cloud mail action copies a draft to clipboard.

## Pilot acceptance

- [ ] Security/privacy and model-provider approval
- [ ] Private HTTPS hostname and single-user SSO working
- [ ] Unauthorized access denied for HTML, API, ZIP and export
- [ ] Only configured Jira analyst's tasks imported
- [ ] Sprint-first order correct; factor score always 0–100
- [ ] Daily job runs when user's laptop is off and reports failure
- [ ] Manual state survives restart and secure backup/restore
- [ ] 20–30 real-case quality review meets target
- [ ] Official AERTiCKET brand guideline approved/applied
- [ ] Corporate security approval for pilot go-live

For managed PostgreSQL, object storage, queues, cloud secret manager,
multi-user isolation and HA, see `docs/CLOUD_MIGRATION_PLAN.md`.
Those production components are NOT implemented in this pilot.
