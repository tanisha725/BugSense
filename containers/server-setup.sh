#!/bin/sh
# Sets up BugSense on a fresh Ubuntu server (made for Oracle Cloud Always Free).
# Run it on the server, inside the downloaded project folder:
#
#   ./containers/server-setup.sh
#
# It installs Podman, opens port 8080, makes the containers start again after
# a reboot, asks for the (optional) Groq key, and starts all five containers.
set -e
cd "$(dirname "$0")/.."

if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
  echo "This script is made for Ubuntu (choose the Ubuntu image on Oracle Cloud)." >&2
  exit 1
fi

echo "== 1/5 Installing Podman (this takes a few minutes) =="
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y podman netavark aardvark-dns pipx curl git iptables-persistent
pipx install podman-compose >/dev/null 2>&1 || pipx upgrade podman-compose >/dev/null 2>&1 || true
export PATH="$HOME/.local/bin:$PATH"
pipx ensurepath >/dev/null 2>&1 || true
podman --version
podman-compose version 2>/dev/null | head -1

echo "== 2/5 Opening port 8080 in the server's own firewall =="
# Oracle's Ubuntu images block every port except SSH. (Port 8080 must ALSO be
# opened in the Oracle Cloud website: see SERVER.md, step 4.)
if ! sudo iptables -C INPUT -p tcp --dport 8080 -m state --state NEW -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 1 -p tcp --dport 8080 -m state --state NEW -j ACCEPT
fi
sudo netfilter-persistent save >/dev/null 2>&1 || true

echo "== 3/5 Making the containers start again after a reboot =="
sudo loginctl enable-linger "$USER"
systemctl --user enable podman-restart.service >/dev/null 2>&1 || true

echo "== 4/5 The AI key (optional) =="
if [ ! -s backend/.env ]; then
  printf "Paste your Groq key (or just press Enter to skip; the free rule engine is used): "
  stty -echo 2>/dev/null || true
  read -r key || key=""
  stty echo 2>/dev/null || true
  echo
  umask 077
  if [ -n "$key" ]; then echo "LLM_API_KEY=$key" > backend/.env; else : > backend/.env; fi
  chmod 600 backend/.env
fi

echo "== 5/5 Building and starting BugSense (the first build takes 5-10 minutes) =="
./podman.sh up

echo
echo "Done. Open  http://<your server's Public IP>:8080  in a browser."
echo "The Public IP is on the instance page in the Oracle Cloud website."
