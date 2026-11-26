# Deploy op Railway (Free plan) zonder dataverlies

Alle data (database, auditlogs en uploads) staat in `/app/data`. Koppel daar één Railway Volume aan,
dan blijft alles bewaard bij elke redeploy.

## Eenmalig instellen

1. **Service**: New Project → Deploy from GitHub repo → kies deze repo. Railway herkent de `Dockerfile` vanzelf.
2. **Volume** (het belangrijkste):
   rechtsklik op de service (of `Ctrl/Cmd + K`) → **Create Volume** → mount path: **`/app/data`**.
3. **Variables** (tab *Variables* van de service):
   | Variabele | Waarde |
   |---|---|
   | `SECRET_KEY` | lange willekeurige tekst (bijv. `python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
   | `SUPERADMIN_SECRET` | andere lange willekeurige tekst |
   | `MIGHTPULSE_API_KEY` | optioneel: API-key van https://api.mightpulse.com (inloggen met Discord → Create API key). Vult naam, avatar en alliance automatisch in na het invullen van een Player ID. Zonder key typen spelers hun naam zelf. |
   | `SESSION_COOKIE_SECURE` | `true` |

   Zonder `SECRET_KEY` en `SUPERADMIN_SECRET` start de app op Railway bewust niet.
4. **Domein**: Settings → Networking → **Generate Domain**. De app luistert op Railway's `$PORT` (meestal 8080); de target port van het domein moet daarmee overeenkomen.

## Controleren

- In de deploy-logs mag **geen** regel `WARNING: no Railway Volume attached` staan.
- Test: maak een event aan, klik *Redeploy*, en kijk of het event er nog is.

## Goed om te weten (Free plan)

- Volume max. 0,5 GB en 1 volume per project: genoeg voor SQLite + logs.
- De service slaapt na 5–10 min zonder verkeer; het eerste verzoek daarna duurt even.
- Bij een redeploy is de app kort offline (Railway koppelt het volume aan één deployment tegelijk).
- Maak af en toe een backup: download `planner.db` met `railway volume files` of `railway ssh`.
