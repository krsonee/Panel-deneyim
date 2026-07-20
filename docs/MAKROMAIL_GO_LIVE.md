# MakroMail go-live checklist

## Render

1. Apply [`render.yaml`](../render.yaml): services `makromail`, `makromail-worker`, DB `makromail-db`.
2. Set `MAILING_SUPERADMIN_PASSWORD` (and sync `SECRET_KEY` / `MAILING_SECRET_KEY` between web+worker).
3. Set `makropanel` env: `SERVICE_MODE=panel`, `MAILING_EMBEDDED=0`, `MAKROMAIL_URL=https://<makromail-host>`.
4. Optional: custom domain for MakroMail; set `PUBLIC_BASE_URL` accordingly (click/open/unsub).

## Data migrate

```bash
SOURCE_DATABASE_URL='postgres://…makropanel…' \
MAILING_DATABASE_URL='postgres://…makromail…' \
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

## Security smoke

- Tenant A cannot list Tenant B campaigns/contacts (tenant_id filter)
- Tenant A cannot use domain not allocated
- Suspended tenant gets 403 on API
- SMTP secrets never returned in tenant `/api/mailing/domains` or settings UI
- Login rate limit after ~20 failures / 5 min

## Cutover

1. Pause campaigns on old panel
2. Migrate
3. Point DNS / bookmark to MakroMail
4. Confirm worker logs resume queued campaigns
5. Remove `MAILING_EMBEDDED=1` if temporarily enabled
