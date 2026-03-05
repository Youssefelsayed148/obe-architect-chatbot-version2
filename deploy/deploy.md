# OBE Architects Bot - Production Deployment

This guide assumes Ubuntu server with Docker + Compose plugin installed.

## 1) Install Docker

```bash
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

Log out and back in to apply group changes.

## 2) Clone repo and configure env

```bash
git clone <YOUR_GITHUB_REPO_URL> /opt/obe-architects-bot
cd /opt/obe-architects-bot
cp .env.production.example .env.production
```

Edit `.env.production` and set real values. Do not commit it.

## 3) Deploy

```bash
./scripts/check_env.sh .env.production
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

## 4) Verify

```bash
curl -i http://127.0.0.1/health
curl -I http://127.0.0.1/widget.js
curl -I http://127.0.0.1/widget.css
```

## 5) Webhook URL

WhatsApp webhook callback URL:

```
https://<your-domain>/webhook/whatsapp
```

## 6) Notes

- Nginx config lives at `docker/nginx.conf`.
- `docker-compose.prod.yml` is the canonical production compose file (a copy is kept in `deploy/docker-compose.prod.yml`).
- Schema is created on app startup (no migrations configured).
