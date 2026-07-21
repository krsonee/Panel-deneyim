# Mikromail go-live checklist

## Render

1. Apply [`render.yaml`](../render.yaml): services `mikromail`, `mikromail-worker`, DB `mikromail-db`.
2. Set `MAILING_SUPERADMIN_PASSWORD` (and sync `SECRET_KEY` / `MAILING_SECRET_KEY` between web+worker).
3. Set `makropanel` env: `SERVICE_MODE=panel`, `MAILING_EMBEDDED=0`, `MIKROMAIL_URL=https://<mikromail-host>`.
4. Optional: custom domain for Mikromail; set `PUBLIC_BASE_URL` accordingly (click/open/unsub).

## Data migrate

```bash
SOURCE_DATABASE_URL='postgres://…makropanel…' \
MAILING_DATABASE_URL='postgres://…mikromail…' \
python scripts/migrate_mailing_to_makromail.py
```

Same-DB transition (dev):

```bash
DATABASE_URL='…' python scripts/migrate_mailing_to_makromail.py
```

## First login

- Superadmin: `MAILING_SUPERADMIN_USER` / password
- Platform → create tenant → allocate domains → select tenant → send test campaign
- Tenant login: `slug/admin`

## Cutover

1. Pause campaigns on old panel
2. Migrate
3. Point DNS / bookmark to Mikromail (`https://mikromail.onrender.com`)
4. Confirm worker logs resume queued campaigns
5. Remove `MAILING_EMBEDDED=1` if temporarily enabled
