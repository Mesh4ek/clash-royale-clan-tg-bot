# Deployment

## CI/CD overview

```
GitHub Actions (manual run) → build → GHCR → deploy over SSH → server
```

- **CI** (`.github/workflows/ci.yml`): lint and a Docker build check on every push and pull request.
- **CD** (`.github/workflows/deploy.yml`): builds the image, pushes it to GHCR and deploys it to the server. It runs manually from the Actions tab (see [Manual deploy](#manual-deploy)); add a `push` trigger to deploy on every push to `main`.

## Server setup

### 1. Install Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 2. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/clash-royale-clan-tg-bot.git ~/clash-royale-clan-tg-bot
cd ~/clash-royale-clan-tg-bot
```

### 3. Configure `.env`

```bash
cp .env.example .env
nano .env  # fill in TELEGRAM_BOT_TOKEN, CLASH_API_TOKEN, etc.
```

## GitHub secrets

In the repository: **Settings → Secrets and variables → Actions**

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | Server IP or hostname |
| `DEPLOY_USER` | SSH user (e.g. `root` or `deploy`) |
| `DEPLOY_SSH_KEY` | Private SSH key for the server |
| `DEPLOY_PORT` | (optional) SSH port, default 22 |
| `DEPLOY_PATH` | (optional) Project path on the server, default `~/clash-royale-clan-tg-bot` |
| `DEPLOY_GHCR_TOKEN` | (optional) PAT with `read:packages` for private images; otherwise `GITHUB_TOKEN` is used |

### Create a deploy SSH key

```bash
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy -N ""
```

Add the public key to `~/.ssh/authorized_keys` on the server and the private key to `DEPLOY_SSH_KEY`.

## Protected environment (optional)

To guard production, add this to the `deploy` job in `deploy.yml`:

```yaml
deploy:
  environment: production
```

Then create `production` under **Settings → Environments** and set protection rules (for example, required reviewers).

## Manual deploy

**Actions → Deploy → Run workflow**

The `skip_build` option only restarts the containers without rebuilding the image.

## Local check

```bash
# Build
docker build -t clash-bot:local .

# Run (with .env in the project root)
docker compose up -d
```
