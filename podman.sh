#!/bin/sh
# BugSense on Podman, in one command.
#
#   ./podman.sh machine    first time only on a Mac: create a small Podman VM (2 CPUs, 2 GB)
#   ./podman.sh up         build and start every container, then open http://localhost:8080
#   ./podman.sh status     which containers run, and their health
#   ./podman.sh failover   show the backup UI taking over: stops web-main, checks, starts it again
#   ./podman.sh logs api   follow one container's output (db, api, web-main, web-backup, gateway)
#   ./podman.sh signup on  let other people create accounts (off: only existing accounts)
#   ./podman.sh update     on a server: download the newest code from GitHub and rebuild
#   ./podman.sh down       stop and remove the containers (the database volume is kept)
set -e
cd "$(dirname "$0")"

compose() {
  if podman compose version >/dev/null 2>&1; then podman compose "$@"
  elif command -v podman-compose >/dev/null 2>&1; then podman-compose "$@"
  else
    echo "No compose tool found. Install one with:  pip3 install podman-compose" >&2
    exit 1
  fi
}

random() { python3 -c "import secrets; print(secrets.token_urlsafe(32))"; }

# The secrets, made once with random values and kept in .env (never committed)
make_env() {
  if [ ! -f .env ]; then
    {
      echo "# Made by ./podman.sh; keep this file private (it is in .gitignore)"
      echo "POSTGRES_PASSWORD=$(random)"
      echo "SECRET_KEY=$(random)"
      echo "INGEST_TOKEN=$(random)"
    } > .env
    chmod 600 .env
    echo "Created .env with new random secrets"
  fi
  # The AI key file; empty means the free rule-based investigator is used
  [ -f backend/.env ] || touch backend/.env
}

served_by() { curl -s --max-time 5 http://localhost:8080/served-by || echo '(no answer)'; }

case "$1" in
  machine)
    podman machine init --cpus 2 --memory 2048 --disk-size 20 2>/dev/null || true
    podman machine start
    ;;
  up)
    make_env
    compose up -d --build
    echo
    echo "BugSense is starting: http://localhost:8080  (the first start takes a minute)"
    ;;
  down)
    compose down
    ;;
  status)
    podman ps --all --filter name=bugsense --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo
    echo "The UI is served by: $(served_by)"
    ;;
  failover)
    echo "1. Now:                      $(served_by)"
    podman stop bugsense-web-main >/dev/null
    echo "2. web-main stopped. Now:    $(served_by)"
    podman start bugsense-web-main >/dev/null
    echo "   web-main started again; the gateway goes back to it within 10 seconds."
    sleep 12
    echo "3. After 12 seconds:         $(served_by)"
    ;;
  signup)
    make_env
    case "$2" in
      on) value=true ;;
      off) value=false ;;
      *) echo "Use: ./podman.sh signup on   or   ./podman.sh signup off" >&2; exit 1 ;;
    esac
    grep -v '^ALLOW_SIGNUP=' .env > .env.new && mv .env.new .env
    echo "ALLOW_SIGNUP=$value" >> .env
    chmod 600 .env
    # Recreate only the API so it reads the new setting (the data stays)
    podman rm -f bugsense-api >/dev/null 2>&1 || true
    compose up -d api
    echo "Sign-up is now $2. Turn it off again once your guests have accounts."
    ;;
  update)
    git pull --ff-only
    make_env
    compose up -d --build
    echo "Updated to the newest code."
    ;;
  logs)
    podman logs --follow "bugsense-${2:-api}"
    ;;
  *)
    sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
