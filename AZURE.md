# Hosten op Azure App Service (Linux-container)

Data (database, auditlogs, uploads) staat in `/home/data` op de persistente App Service-opslag.
Die opslag is een netwerkshare (Azure Files), daarom draait SQLite hier **zonder WAL** en op **één instance**.

## Eenmalig aanmaken (Azure CLI / Cloud Shell, Bash)

Voer uit vanuit de map van deze repo. Kies unieke namen voor `ACR` en `APP`.

```bash
RG=kvkprep-rg
LOC=westeurope
ACR=kvkprepacr$RANDOM          # alleen kleine letters/cijfers
PLAN=kvkprep-plan
APP=kvkprep-$RANDOM            # wordt https://$APP.azurewebsites.net

# 1. Resource group + container registry, en image bouwen in Azure
az group create -n $RG -l $LOC
az acr create -g $RG -n $ACR --sku Basic
az acr build -r $ACR -t kvkprep:latest .

# 2. Linux App Service-plan + web app (B1 is het kleinste plan met 'Always On')
az appservice plan create -g $RG -n $PLAN --is-linux --sku B1
az webapp create -g $RG -p $PLAN -n $APP --container-image-name $ACR.azurecr.io/kvkprep:latest

# 3. Image ophalen met managed identity (geen registry-wachtwoord nodig)
PID=$(az webapp identity assign -g $RG -n $APP --query principalId -o tsv)
ACR_ID=$(az acr show -g $RG -n $ACR --query id -o tsv)
az role assignment create --assignee $PID --scope $ACR_ID --role AcrPull
az acr config authentication-as-arm update -r $ACR --status enabled
az webapp config set -g $RG -n $APP --generic-configurations '{"acrUseManagedIdentityCreds": true}'

# 4. Instellingen
az webapp config appsettings set -g $RG -n $APP --settings \
  WEBSITES_PORT=5000 \
  WEBSITES_ENABLE_APP_SERVICE_STORAGE=true \
  DATA_DIR=/home/data \
  DATABASE_PATH=/home/data/planner.db \
  SQLITE_JOURNAL_MODE=DELETE \
  WEB_CONCURRENCY=1 \
  GUNICORN_THREADS=4 \
  SESSION_COOKIE_SECURE=true \
  SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  SUPERADMIN_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"

# Optioneel MIGHTPULSE_API_KEY (spelersnaam/avatar opzoeken) apart zetten, niet in je shell-history:
#   Portal → App Service → Settings → Environment variables → + Add

az webapp update -g $RG -n $APP --https-only true
az webapp config set -g $RG -n $APP --always-on true
az webapp restart -g $RG -n $APP
```

Het superadmin-geheim terugvinden: Portal → App Service → *Environment variables* → `SUPERADMIN_SECRET`.

## Nieuwe versie uitrollen

```bash
az acr build -r $ACR -t kvkprep:latest .
az webapp restart -g $RG -n $APP
```

De data in `/home/data` blijft daarbij staan.

## Controleren

```bash
az webapp log config -g $RG -n $APP --docker-container-logging filesystem
az webapp log tail -g $RG -n $APP
```

- Er mag **geen** regel `WARNING: ... DATA_DIR ... must be under /home` in staan.
- `NOTE: cannot hand /home/data to appuser ... running as root` is normaal op App Service.
- Test: maak een event aan, `az webapp restart`, en kijk of het event er nog is.

## Belangrijk

- **Niet uitschalen** (instance count = 1). SQLite op een netwerkshare met meerdere instances kan de database beschadigen.
- **Bestaande data meenemen** (bijv. van Railway): zet `planner.db` via Kudu
  (`https://$APP.scm.azurewebsites.net` → Debug console) in `/home/data/` en herstart.
  Een WAL-database wordt bij de eerste start automatisch omgezet.
- **Backup**: download `/home/data/planner.db` periodiek via Kudu, of gebruik App Service Backup
  als je plan dat ondersteunt.
- Wordt de app drukker of wil je meerdere instances: stap dan over op Azure Database for PostgreSQL;
  dat vraagt een aanpassing van `app/database.py`.
