# Running BugSense on Podman

Every part of BugSense runs in its own **container**. Podman starts them all
from one file, [`compose.yaml`](compose.yaml).

```
 browser  ──►  gateway (http://localhost:8080)
                 ├──►  web-main     the UI (React, served by nginx)
                 ├──►  web-backup   the same UI; used only when web-main is down
                 └──►  api          FastAPI + the demo shop  ──►  db (PostgreSQL)
```

| Container | What it is | Image |
|---|---|---|
| `bugsense-gateway` | The front door on port 8080. Sends `/api/...` to the API and every page to the UI, and switches to the backup UI when the main one does not answer | nginx 1.28 |
| `bugsense-web-main` | The main UI | built from `containers/web.Containerfile` |
| `bugsense-web-backup` | The backup UI: the same image, a second copy | the same image |
| `bugsense-api` | The backend; it also runs the demo shop, which sends **live OpenTelemetry** to it | built from `containers/api.Containerfile` |
| `bugsense-db` | PostgreSQL; its files live in the volume `bugsense-db-data`, so data survives restarts | postgres 17 |

Every container has `restart: always` and a health check, so one that crashes
is started again by Podman.

---

## 1. Install Podman (once)

1. Download the Podman installer for macOS from **podman.io** (the `.pkg`
   file) and open it.
2. Install the compose tool: `pip3 install podman-compose`
3. On a Mac, Podman runs containers inside a small Linux virtual machine.
   Create a **light** one (2 CPUs, 2 GB memory), so the Mac stays fast:

   ```
   ./podman.sh machine
   ```

   (This runs `podman machine init --cpus 2 --memory 2048` and
   `podman machine start`.) The containers together are limited to about
   1.2 GB of memory (see `mem_limit` in `compose.yaml`).

## 2. Start BugSense

```
./podman.sh up
```

The first time, Podman downloads the base images and builds the three
BugSense images; that takes a few minutes. After that it is quick.

It also creates the file `.env` with random secrets (database password,
`SECRET_KEY`, `INGEST_TOKEN`). That file is private and never goes to GitHub.
The AI key is read from `backend/.env`, the same file as for the local run.

Open **http://localhost:8080**, create the owner account, and use BugSense as
usual. The top bar shows a green pill **UI · web-main**: the main container
served the page.

## 3. See the live data through telemetry

1. **Services** → **Start all**. The demo shop starts inside the `api`
   container and sends traces and metrics over OpenTelemetry.
2. **Telemetry**: the **LIVE** badge pulses, each service has a green or red
   sentence, and the page refreshes every 5 seconds.
3. Break something (Services → stop `shop-db`) and watch Telemetry turn red,
   then open the new incident and press **Find probable cause**.

## 4. Show the backup UI taking over

```
./podman.sh failover
```

It prints which container serves the UI, stops `web-main`, prints again
(now **web-backup**), starts `web-main` again and prints a third time. In the
browser the pill turns yellow (**Backup UI · web-backup**) while the main one
is down, and the site keeps working. To do it by hand:

```
podman stop bugsense-web-main     # the site keeps working on web-backup
podman start bugsense-web-main    # within 10 seconds the gateway uses it again
```

**How the switch works:** the gateway (nginx) lists web-main as the normal
server and web-backup as a `backup` server. If web-main does not answer
within 2 seconds, nginx sends the same request to web-backup, and keeps using
the backup for 10 seconds before trying web-main again. The user sees no
error page.

## 5. Everyday commands

| Command | What it does |
|---|---|
| `./podman.sh status` | Lists the containers, their health, and which UI is serving |
| `./podman.sh logs api` | Follows one container's output (`db`, `api`, `web-main`, `web-backup`, `gateway`) |
| `./podman.sh up` | After a code change: rebuilds what changed and restarts it |
| `./podman.sh signup on` / `off` | Lets other people create accounts, or stops it |
| `./podman.sh down` | Stops and removes the containers; the database volume is kept |
| `podman machine stop` | Stops the virtual machine, freeing its memory |

To delete the data as well: `podman volume rm bugsense_bugsense-db-data`
(after `down`).

## 6. Sending telemetry from your own program

The gateway also passes OpenTelemetry through, so any program on the Mac can
report to the containers:

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8080
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20<INGEST_TOKEN from .env>
```

## If something goes wrong

| What you see | What to do |
|---|---|
| `podman: command not found` | Install Podman (step 1) and open a new terminal |
| `Cannot connect to Podman` | The machine is not running: `podman machine start` |
| `No compose tool found` | `pip3 install podman-compose` |
| The site says "Cannot reach the BugSense server" | The API is still starting (it waits for the database): `./podman.sh logs api` |
| Port 8080 is already in use | Change `"8080:8080"` in `compose.yaml` to `"8090:8080"` and open port 8090 |
| The Mac gets slow | `podman machine stop` when you are not using it |

## Putting it online

To share BugSense with others, run the same containers on a free Oracle
Cloud server: [SERVER.md](SERVER.md).

## The files

| File | What it does |
|---|---|
| `compose.yaml` | The five containers, their network (fixed addresses 10.90.7.x), volume, limits and restart policy |
| `containers/api.Containerfile` | Python 3.13 image with the backend and the demo shop; runs as a normal user, not root |
| `containers/web.Containerfile` | Builds the React app with Node, then serves only the built files with nginx |
| `containers/web.nginx.conf.template` | One UI container; answers `/served-by` with its name |
| `containers/gateway.Containerfile`, `gateway.nginx.conf` | The front door and the switch to the backup |
| `containers/wait_for_db.py` | Makes the API wait until PostgreSQL is ready |
| `.containerignore` | Keeps secrets (`.env`), `venv` and `node_modules` out of the images |
| `podman.sh` | The short commands above |
