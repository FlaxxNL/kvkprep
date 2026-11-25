#!/bin/sh
set -e

# All persistent state lives under DATA_DIR so a single volume (e.g. one
# Railway Volume mounted at /app/data) keeps database, audit logs and uploads.
DATA_DIR="${DATA_DIR:-/app/data}"
mkdir -p "$DATA_DIR" "$DATA_DIR/logs" "$DATA_DIR/uploads" /home/appuser

# Point the legacy log/upload locations at the persistent data dir.
for pair in "/app/logs:$DATA_DIR/logs" "/app/app/static/uploads:$DATA_DIR/uploads"; do
    link="${pair%%:*}"
    target="${pair#*:}"
    if [ ! -L "$link" ]; then
        # Move anything already there (e.g. from an older image) before linking.
        if [ -d "$link" ]; then
            cp -a "$link"/. "$target"/ 2>/dev/null || true
            rm -rf "$link"
        fi
        ln -s "$target" "$link"
    fi
done

# Warn loudly when running on Railway without a volume: data would be lost on redeploy.
if [ -n "$RAILWAY_ENVIRONMENT" ] && [ -z "$RAILWAY_VOLUME_MOUNT_PATH" ]; then
    echo "WARNING: no Railway Volume attached. All data in $DATA_DIR will be LOST on the next redeploy." >&2
    echo "WARNING: add a Volume to this service with mount path $DATA_DIR." >&2
elif [ -n "$RAILWAY_VOLUME_MOUNT_PATH" ] && [ "$RAILWAY_VOLUME_MOUNT_PATH" != "$DATA_DIR" ]; then
    echo "WARNING: Railway Volume is mounted at $RAILWAY_VOLUME_MOUNT_PATH but DATA_DIR is $DATA_DIR. Data will NOT persist." >&2
fi

# Azure App Service: data must be on the persistent /home share.
if [ -n "$WEBSITE_SITE_NAME" ]; then
    case "$DATA_DIR" in
        /home/*) ;;
        *) echo "WARNING: on App Service DATA_DIR ($DATA_DIR) must be under /home or data is LOST on restart." >&2 ;;
    esac
fi

# Fix volume permissions if running as root. Network shares such as Azure Files
# do not support chown; in that case keep running as root instead of failing.
if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser /home/appuser 2>/dev/null || true
    if chown -R appuser:appuser "$DATA_DIR" 2>/dev/null && chmod -R 775 "$DATA_DIR" 2>/dev/null \
        && gosu appuser test -w "$DATA_DIR"; then
        exec gosu appuser "$@"
    fi
    echo "NOTE: cannot hand $DATA_DIR to appuser (network share?); running as root." >&2
fi

exec "$@"
