# Backup Strategy

## Scope

This documents the backup posture for the Postgres database that backs
every piece of user/business state in Baseerah (accounts, subscriptions,
invoices, portfolios, audit logs, etc.). It deliberately does **not**
cover write-ahead-log (WAL) archiving or point-in-time recovery (PITR) --
that's real operational complexity (a WAL-shipping target, a restore
runbook someone has actually rehearsed, monitoring for archive-lag) that
isn't justified before there's a paying customer and real data to lose
between backups. What's below is the minimum that makes "we deleted
something in production" or "the disk died" recoverable within a day,
not a zero-data-loss guarantee.

## What's backed up

A daily `pg_dump` of the full `basirah` database, taken as a custom-format
dump (`-Fc`) so it restores with `pg_restore` (supports parallel restore
and selective table/schema restore, unlike a plain SQL dump).

## How

A dedicated backup sidecar container, run via `docker compose run` from
a host cron entry (not baked into `docker-compose.yml`'s always-on
services -- a backup job has a start/finish, not a "keep running"
lifecycle):

```bash
# /etc/cron.d/basirah-backup (on the host running docker-compose)
0 3 * * * root cd /opt/basirah && \
  docker compose exec -T db pg_dump -Fc -U "$POSTGRES_USER" basirah_db \
  > /opt/basirah/backups/basirah-$(date +\%Y\%m\%d).dump 2>> /opt/basirah/backups/backup.log
```

## Retention

7 days, local disk, pruned by the same cron entry:

```bash
find /opt/basirah/backups -name 'basirah-*.dump' -mtime +7 -delete
```

7 days covers "someone fat-fingered a delete this week," which is the
actual risk this exists to cover today. Off-host/off-site retention
(S3, a second region) is the natural next step once there's revenue and
a real disaster-recovery requirement to size it against -- not before.

## Restore

```bash
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d basirah_db \
  --clean --if-exists < /opt/basirah/backups/basirah-YYYYMMDD.dump
```

`--clean --if-exists` drops existing objects before recreating them, so
this is safe to run against a database that already has (stale) data in
it, not just an empty one.

## What this does not cover

- **Point-in-time recovery.** A daily dump means up to 24h of data loss
  in the worst case (a failure minutes before the next scheduled dump).
  Acceptable today; not acceptable once there are paying subscribers
  with real transaction history -- WAL archiving is the correct next
  step at that point, not a smaller cron interval.
- **Redis.** Redis here is a fast-path cache/allowlist
  (`src/auth/token_store.py`) whose durable source of truth is already
  Postgres (`UserSession.revoked_at`) -- losing it degrades to "every
  session needs to re-authenticate," never to data loss, so it is
  intentionally not backed up.
- **Off-host storage.** Backups above live on the same host as the
  database they back up. A host-level disk failure takes out both the
  primary and its backups. Documented here as a known gap, not a
  silent one.
