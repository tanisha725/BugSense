# Sharing BugSense: a public link on Render

BugSense has two deployments, both free:

| | Podman ([PODMAN.md](PODMAN.md), [SERVER.md](SERVER.md)) | Render (this guide) |
|---|---|---|
| Purpose | The full containerised setup | A public link anyone can try |
| Containers | gateway, web-main, **web-backup**, api, db | The same **api** and **web** images, plus Render's database |
| Backup UI | Yes (the gateway switches to web-backup) | No (Render runs one copy of each) |
| Runs on | Your Mac, or a free Oracle server | Render's servers |

Render builds the **same container images** as Podman, from
`containers/api.Containerfile` and `containers/web.Containerfile`. The file
[`render.yaml`](render.yaml) describes everything, so Render creates all
three parts in one go:

| Part | On Render | What it is |
|---|---|---|
| `bugsense-api` | Web service (container) | The FastAPI backend; it also runs the demo shop, which sends live telemetry |
| `bugsense-web` | Web service (container) | The React UI, served by nginx |
| `bugsense-db` | PostgreSQL | The database |

## Free plan: what to expect

Render's free limits change, so check Render's pricing page. Today:

- **It sleeps when nobody uses it** (after about 15 minutes). The next visitor
  waits about a minute while it wakes up. Open the link a few minutes before
  showing it to someone.
- **While it sleeps, the demo shop sleeps too**, so live telemetry starts again
  when someone opens the site and presses Services → Start all.
- **The free database is time-limited** (about 30 days). When Render says it
  will expire, create a new one from the dashboard and import the datasets
  again.

---

## Step 1: Create a Render account

Go to **render.com** and sign up **with GitHub**. That lets Render see your
`BugSense` repository.

## Step 2: Create everything from the Blueprint

1. In the Render dashboard click **New** → **Blueprint**.
2. Pick the **BugSense** repository.
3. Render reads `render.yaml` and lists the three parts.
4. It asks for **LLM_API_KEY**: paste your Groq key (Render keeps it secret;
   it never goes to GitHub). You can leave it empty: then the free rule
   engine diagnoses incidents.
5. Click **Apply** (or **Deploy Blueprint**).

The first build takes about 10 minutes (Render builds both container images).
When it is done, all three parts show **Live** (or **Available** for the
database).

## Step 3: Check the two addresses

`render.yaml` assumes Render's usual addresses:

- backend: `https://bugsense-api.onrender.com`
- UI: `https://bugsense-web.onrender.com`

Open each service in the dashboard and look at the address at the top.
**If both match**, there is nothing to do.

**If Render gave a different address** (because the name was taken):

1. **bugsense-web** → **Environment** → set `VITE_API_URL` to the backend's
   real address → save → **Manual Deploy** → **Deploy latest commit** (the UI
   is built with this address inside it).
2. **bugsense-api** → **Environment** → set `FRONTEND_URL` to the UI's real
   address → save (it restarts by itself).

## Step 4: Get it ready for visitors

1. Open the **UI's address**. Create your account first (the first account is
   the owner).
2. **Datasets**: import a few datasets, so visitors see incidents straight away.
3. **Services** → **Start all**, so Telemetry shows live data.
4. The top bar shows **UI · render**: the page came from the UI container.

## Step 5: Share the link

Send people `https://bugsense-web.onrender.com`. Sign-up is **open**
(`ALLOW_SIGNUP=true`), so visitors create their own account and try
everything.

Everyone shares the same data. A visitor could delete logs or stop the demo
shop; if that happens, import the datasets again. To close sign-up:
**bugsense-api** → **Environment** → `ALLOW_SIGNUP` = `false`.

The AI diagnosis uses your free Groq quota. If many visitors use it at once,
diagnoses wait for the free tier's per-minute limit; the **Rules** engine is
always free and instant.

## Updates

Every `git push` to `main` makes Render rebuild and deploy both containers by
itself. The data stays in the database.

---

## What protects the online version

| Setting (on bugsense-api) | Made by | What it does |
|---|---|---|
| `SECRET_KEY` | Render, random | Signs the sign-in tokens, so they cannot be forged |
| `INGEST_TOKEN` | Render, random | Only programs that know it may send OpenTelemetry data; the demo shop gets it automatically |
| `LLM_API_KEY` | You | Your Groq key, kept by Render, never in GitHub |
| `ALLOW_SIGNUP` | `true` | Visitors may create accounts; set `false` to close |

Passwords are stored as scrypt hashes, and Render serves everything over
https.

## If something goes wrong

| What you see | What to do |
|---|---|
| The page takes a minute to open | Normal on the free plan: it was asleep |
| "Cannot reach the BugSense server" | The backend is still waking up: wait a minute and reload. If it stays, check `VITE_API_URL` (Step 3) |
| Signing in works, but every page shows errors | `FRONTEND_URL` on the backend does not match the UI's address (Step 3) |
| A build fails | Open the service → **Logs**: the last lines say why |
| AI diagnosis says "no AI key" | Set `LLM_API_KEY` on bugsense-api → Environment |

## Backup for the presentation

Keep Podman ready on your Mac (`./podman.sh up`). If the internet or Render
lets you down, the full setup, including the backup UI, runs on your laptop.
