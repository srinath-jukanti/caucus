#!/bin/bash
# Headless scheduled Caucus briefing — the reference deployment's launcher.
# Adjust CAUCUS_DIR and ENVF, then schedule with cron or the launchd template.
set -uo pipefail

CAUCUS_DIR="${CAUCUS_DIR:-$HOME/caucus-live}"
ENVF="${CAUCUS_ENV_FILE:-$CAUCUS_DIR/.env}"

cd "$CAUCUS_DIR" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Secrets stay in an env file (never in config.yaml): the Claude Code OAuth
# token for headless runs and the SMTP credentials for the email notifier.
for var in CLAUDE_CODE_OAUTH_TOKEN GMAIL_ADDRESS GMAIL_APP_PASSWORD; do
  value=$(grep -E "^${var}=" "$ENVF" 2>/dev/null | head -1 | cut -d= -f2-)
  [ -n "$value" ] && export "$var"="$value"
done

mkdir -p logs
TS=$(date +%Y%m%d-%H%M)
caucus briefing >> "logs/run-${TS}.log" 2>&1
RC=$?
echo "$(date '+%Y-%m-%d %H:%M:%S') rc=${RC}" >> logs/run-history.log
exit $RC
