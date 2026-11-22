# Deploying BugSense

> **Main deployment: Podman on Oracle Cloud (free), see [SERVER.md](SERVER.md).**
> Render, below, is an alternative that does not use containers.

BugSense goes online on **Render**, straight from the GitHub repository. No
Docker is needed: Render builds everything on its own servers. The file
[`render.yaml`](render.yaml) describes the whole setup, so Render creates
all three parts in one go:

| Part | On Render | What it is |
|---|---|---|
| `bugsense-api` | Web service (Python) | The FastAPI backend; it also runs the demo shop |
| `bugsense-web` | Static site | The React frontend |
| `bugsense-db` | PostgreSQL | The database |

Free plans are used everywhere. Their limits change, so check Render's
pricing page. Two things to know:

- A free web service **goes to sleep** when nobody uses it. The first visit
  after that takes about a minute while it wakes up. Open the site a few
  minutes before a presentation.
- Free databases on Render are **time-limited**. For a long-lived
  deployment, check Render's current terms.

---

## Before you start

1. The latest code is pushed to GitHub (`main` branch).
2. You have your free Groq key at hand (the same one as in `backend/.env`).

## Step 1: Create a Render account

Go to **render.com** and sign up **with GitHub**. That lets Render see your
`BugSense` repository.

## Step 2: Create everything from the Blueprint

1. In the Render dashboard click **New** → **Blueprint**.
2. Pick the **BugSense** repository.
3. Render reads `render.yaml` and lists the three parts.
4. It asks for **LLM_API_KEY**: paste your Groq key. (Render keeps it secret;
   it never goes into GitHub.)
5. Click **Apply** (or **Deploy Blueprint**).

The first build takes a few minutes. When it is done, all three parts show
**Live** (or **Available** for the database).

## Step 3: Check the two addresses

The frontend needs the backend's address, and the backend must allow the
frontend's address. `render.yaml` assumes Render's usual addresses:

- backend: `https://bugsense-api.onrender.com`
- frontend: `https://bugsense-web.onrender.com`

Open each service in the dashboard and look at the address shown at the top.

**If both match**, there is nothing to do.

**If Render gave a different address** (for example `bugsense-api-x7k2.onrender.com`
because the name was taken):

1. Open **bugsense-web** → **Environment** → set `VITE_API_URL` to the
   backend's real address → save. Then **Manual Deploy** → **Deploy latest
   commit** (the frontend has to be built again to use the new address).
2. Open **bugsense-api** → **Environment** → set `FRONTEND_URL` to the
   frontend's real address → save (the backend restarts by itself).

## Step 4: First visit

1. Open the **frontend's address** in the browser.
2. It shows **Create the owner account**: enter your name, email and a
   password (at least 8 characters). This first account owns the
   deployment. After it, sign-up closes, so strangers cannot get in.
3. Go to **Datasets** and import the datasets you want to show (the online
   database starts empty).
4. Go to **Services** → **Start all** to run the demo shop online.

To let a teammate create an account, set `ALLOW_SIGNUP=true` on
**bugsense-api** for a moment, and set it back to `false` afterwards.

## Step 5: Updates later

Every `git push` to `main` makes Render build and deploy the new version by
itself.

---

## What protects the online version

| Setting (on bugsense-api) | Made by | What it does |
|---|---|---|
| `SECRET_KEY` | Render, random | Signs the sign-in tokens, so they cannot be forged |
| `INGEST_TOKEN` | Render, random | Only programs that know it may send OpenTelemetry data; the demo shop gets it automatically |
| `LLM_API_KEY` | You | Your Groq key, kept by Render, never in GitHub |
| `ALLOW_SIGNUP` | Not set (off) | After the first account, nobody else can sign up |

To send telemetry from another program to the online BugSense, use:

```
OTEL_EXPORTER_OTLP_ENDPOINT=https://<backend address>
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20<INGEST_TOKEN>
```

## If something goes wrong

| What you see | What to do |
|---|---|
| The site says "Cannot reach the BugSense server" | The backend is asleep or still starting: wait a minute and reload. If it stays, check `VITE_API_URL` (Step 3) |
| Signing in works, but every page shows errors | `FRONTEND_URL` on the backend does not match the frontend's address (Step 3) |
| A build fails | Open the service → **Logs**: the last lines say why |
| AI diagnosis says "no AI key" | Set `LLM_API_KEY` on bugsense-api → Environment |

## Backup for the presentation

Keep the local version ready (see README "Setup"). If the internet or the
host lets you down, BugSense runs the same on your laptop.
