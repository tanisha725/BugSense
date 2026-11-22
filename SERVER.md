# Putting BugSense online: Oracle Cloud (free) + Podman

This puts the **same Podman setup** you run on your Mac (gateway, main UI,
backup UI, API, database) on a free server in the cloud. Anyone with the link
can open it, 24 hours a day, even when your Mac is off.

**Cost: 0.** Oracle's "Always Free" tier includes an Ampere (ARM) server with
up to 4 CPUs and 24 GB of memory. BugSense needs about 1.2 GB. Oracle asks for
a card only to check that you are a real person. A free account is **not
charged** unless you choose "Upgrade to Pay As You Go", so don't click that.

```
 anyone's browser ──► http://<server IP>:8080 ──► Oracle server (Ubuntu + Podman)
                                                    ├─ gateway
                                                    ├─ web-main + web-backup
                                                    ├─ api (+ live demo shop)
                                                    └─ db
```

Total time: about 45 minutes, most of it waiting.

---

## Step 0: Put the newest code on GitHub

The server downloads BugSense from GitHub, so the latest version must be
pushed first (commit and push from the Mac).

## Step 1: Create the Oracle Cloud account

1. Go to **oracle.com/cloud/free** and click **Start for free**.
2. Fill in your details. For **Home Region**, pick the one closest to you
   (for India: Mumbai or Hyderabad). **It cannot be changed later**, and free
   servers can only be made in the home region.
3. Add a card for verification (no money is taken; at most a small
   temporary hold that is returned).
4. Wait for the "Your account is ready" email, then sign in.

## Step 2: Create the server

1. In the Oracle Cloud website, open the menu (☰) → **Compute** →
   **Instances** → **Create instance**.
2. **Name:** `bugsense`
3. **Image and shape** → **Edit**:
   - **Image** → **Change image** → **Ubuntu** → pick **Canonical Ubuntu
     24.04** → **Select image**.
   - **Shape** → **Change shape** → **Ampere** → **VM.Standard.A1.Flex**.
     Set **2 OCPUs** and **12 GB** memory. It must say **Always Free-eligible**.
4. **Networking:** keep "Create new virtual cloud network" and "Create new
   public subnet". Make sure **Assign a public IPv4 address** is on.
5. **Add SSH keys:** choose **Generate a key pair for me** and click
   **Save private key**. Keep that file safe: it is the key to your server.
6. Click **Create**. After a minute or two the state turns green: **Running**.

> **"Out of capacity"?** Free Ampere servers are popular. Try another
> **Availability domain** (in the Placement section), or choose 1 OCPU and
> 6 GB (still plenty), or try again a few hours later.

## Step 3: Note the server's address

On the instance page, copy the **Public IP address** (for example
`140.238.1.2`). Below, write it wherever you see `<IP>`.

## Step 4: Open port 8080 in Oracle's firewall

Oracle blocks every port except SSH until you allow it.

1. On the instance page, click the **Subnet** link (under Primary VNIC).
2. Open **Security Lists** → **Default Security List for ...**.
3. Click **Add Ingress Rules** and fill in:
   - **Source CIDR:** `0.0.0.0/0`
   - **IP Protocol:** TCP
   - **Destination Port Range:** `8080`
4. Click **Add Ingress Rules**.

## Step 5: Connect to the server from your Mac

In the Mac's **Terminal**:

```
mkdir -p ~/.ssh
mv ~/Downloads/ssh-key-*.key ~/.ssh/bugsense.key
chmod 600 ~/.ssh/bugsense.key
ssh -i ~/.ssh/bugsense.key ubuntu@<IP>
```

The first time it asks "Are you sure you want to continue connecting?": type
`yes`. The prompt changes to `ubuntu@bugsense:~$`. You are now typing **on
the server**.

## Step 6: Install and start BugSense (on the server)

Copy these two lines:

```
git clone https://github.com/tanisha725/BugSense.git
cd BugSense && ./containers/server-setup.sh
```

The script does everything:

1. installs Podman,
2. opens port 8080 in the server's own firewall,
3. makes the containers start again by themselves after a reboot,
4. asks for your **Groq key** (paste it and press Enter; nothing is shown
   while you paste, which is normal. Or just press Enter to skip),
5. builds and starts the five containers. The first build takes 5–10 minutes.

When it says **Done**, check it:

```
./podman.sh status
```

You should see five containers, all **Up**.

## Step 7: Open it and create your account

1. In your browser, open **http://\<IP\>:8080**.
2. Create the **owner account** (this online copy has its own, empty
   database).
3. **Services** → **Start all**, then **Telemetry**: the LIVE badge pulses.
4. **Datasets**: import the datasets you want to show, or upload your logs.

## Step 8: Share it

Send people the link `http://<IP>:8080`. To let them in, either:

- **Give them a demo account:** turn sign-up on, create a "Demo" account
  yourself, turn sign-up off, and share that email and password.
- **Let them sign up themselves**, on the server:

  ```
  cd ~/BugSense
  ./podman.sh signup on     # people can create accounts now
  ./podman.sh signup off    # close it again afterwards
  ```

## Updating after you change something

1. On the Mac: test on localhost, then commit and push.
2. On the server:

   ```
   ssh -i ~/.ssh/bugsense.key ubuntu@<IP>
   cd BugSense && ./podman.sh update
   ```

   It downloads the new code and rebuilds only what changed. The data stays.

## Good to know

- **It is plain http, not https.** Fine for a student demo, but don't reuse an
  important password for your BugSense account. (A padlock needs a domain
  name and a certificate; that can be added later.)
- **Idle servers:** Oracle may reclaim an Always Free server that stays almost
  completely idle for a week. The running demo shop keeps it a little busy;
  open the site now and then.
- **Backup UI works here too:** on the server, `./podman.sh failover` shows
  web-backup taking over.
- **Your secrets stay on the server:** `.env` (database password, signing
  key, ingest token) and `backend/.env` (Groq key) are made on the server,
  readable only by you, and never go to GitHub.

## If something goes wrong

| What you see | What to do |
|---|---|
| `ssh: Connection timed out` | Check the IP; the instance must be **Running** |
| `Permission denied (publickey)` | Use the key file from Step 2, and the user name `ubuntu` |
| `UNPROTECTED PRIVATE KEY FILE` | Run `chmod 600 ~/.ssh/bugsense.key` |
| Browser can't open `http://<IP>:8080` | Check Step 4's rule, then on the server `./podman.sh status` |
| A container keeps restarting | `./podman.sh logs api` (or `db`, `gateway`) and read the last lines: they say what went wrong |
| You closed Terminal during setup | Connect again (Step 5) and run `cd BugSense && ./podman.sh up` |
