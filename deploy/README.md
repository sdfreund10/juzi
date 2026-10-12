# Production deploy (DigitalOcean droplet)

Bare-metal production on a single Ubuntu droplet: Postgres on-box, gunicorn behind nginx, TLS via certbot. Local development is unchanged; there is no staging environment yet.

The SPA is **built in GitHub Actions** and copied to the droplet. The box does not need Node.js.

## Architecture

```
Client --HTTPS--> nginx (certbot) --HTTP--> gunicorn :8000 --> Django + WhiteNoise --> Postgres
```

App code lives in `/var/www/juzi`. Secrets live in `/etc/juzi.env` (not in git).
`frontend/dist` is synced from CI (gitignored; not built on the droplet).

## One-time droplet bootstrap

Replace `YOUR_DOMAIN` everywhere with the production hostname.

### 1. Droplet and DNS

1. Create an Ubuntu 24.04 droplet (1 GB RAM is enough to start).
2. Firewall: allow SSH (22), HTTP (80), HTTPS (443).
3. Point `YOUR_DOMAIN` A record at the droplet IP; wait for DNS to resolve.

### 2. System packages

```bash
sudo apt update
sudo apt install -y \
  build-essential curl git nginx postgresql postgresql-contrib rsync \
  python3.12 python3.12-venv python3-certbot-nginx
```

No Node.js on the droplet — Vite builds run in CI. Install `uv` after creating the `juzi` user (next section).

### 3. App user, uv, and directories

Use a normal home for SSH keys; keep the app tree under `/var/www/juzi`.

```bash
sudo adduser --system --group --home /home/juzi --shell /bin/bash juzi
sudo mkdir -p /var/www/juzi
sudo chown juzi:juzi /var/www/juzi
```

Install `uv` as `juzi` (not root). A root install lands in `/root/.local/bin` and is invisible to the app user / CI SSH sessions:

```bash
sudo -u juzi -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
# Non-interactive SSH often has a minimal PATH — put uv on the system path:
sudo ln -sf /home/juzi/.local/bin/uv /usr/local/bin/uv
sudo -u juzi -H bash -lc 'command -v uv && uv --version'
```

Allow passwordless restart of the app unit (needed by `deploy/deploy.sh` and GitHub Actions):

```bash
# Use the real systemctl path (Ubuntu: usually /usr/bin/systemctl, not /bin/...).
echo "juzi ALL=(root) NOPASSWD: $(command -v systemctl) restart juzi, $(command -v systemctl) status juzi" \
  | sudo tee /etc/sudoers.d/juzi
sudo chmod 440 /etc/sudoers.d/juzi
sudo -u juzi sudo -n systemctl status juzi   # must work with no password prompt
```

### 4. PostgreSQL

```bash
sudo -u postgres createuser juzi
sudo -u postgres createdb -O juzi juzi
sudo -u postgres psql -c "ALTER USER juzi WITH PASSWORD 'choose-a-strong-password';"
```

Use a local peer/password URL in the env file below (`localhost`). Do not expose Postgres on the public interface.

### 5. Environment file

`/etc/juzi.env` is both a systemd `EnvironmentFile` (no shell expansion) and
sourced by `deploy/deploy.sh`. Write it in a form both accept: plain
`KEY=value` lines, and **single-quote** any value that contains `$` or other
shell metacharacters (e.g. `DJANGO_SECRET_KEY='prefix$suffix'`). Unquoted `$`
can abort deploy under `set -u` while Gunicorn still gets the literal string.

```bash
sudo tee /etc/juzi.env >/dev/null <<'EOF'
DJANGO_SECRET_KEY='replace-with-a-long-random-string'
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=YOUR_DOMAIN
CSRF_TRUSTED_ORIGINS=https://YOUR_DOMAIN
DATABASE_URL='postgres://juzi:choose-a-strong-password@localhost:5432/juzi'
EOF
sudo chown root:juzi /etc/juzi.env
sudo chmod 640 /etc/juzi.env
```

### 6. Deploy key and clone

The droplet pulls code over SSH as `juzi`, so that user needs a **GitHub deploy key** (separate from the `DROPLET_SSH_KEY` Actions uses to SSH *into* the box).

```bash
sudo -u juzi -H mkdir -p /home/juzi/.ssh
sudo -u juzi -H chmod 700 /home/juzi/.ssh
sudo -u juzi -H ssh-keygen -t ed25519 -f /home/juzi/.ssh/id_ed25519 -N "" -C "juzi-github-key"
sudo -u juzi -H bash -c 'ssh-keyscan -t ed25519,rsa github.com >> /home/juzi/.ssh/known_hosts'
sudo -u juzi -H chmod 600 /home/juzi/.ssh/known_hosts

# Print the public key, then add it in GitHub:
#   repo → Settings → Deploy keys → Add deploy key (read-only is enough)
sudo -u juzi -H cat /home/juzi/.ssh/id_ed25519.pub
```

After the deploy key is saved on GitHub (and `/var/www/juzi` exists and is owned by `juzi` from section 3):

```bash
sudo -u juzi -H git clone git@github.com:sdfreund10/juzi.git /var/www/juzi
```

Ensure `uv` is on `juzi`'s PATH (login shell or `/etc/environment` / `/usr/local/bin`).

### 7. systemd and nginx

```bash
sudo cp /var/www/juzi/deploy/juzi.service /etc/systemd/system/juzi.service
sudo systemctl daemon-reload

sudo cp /var/www/juzi/deploy/nginx-juzi.conf /etc/nginx/sites-available/juzi
sudo sed -i 's/YOUR_DOMAIN/juzi.sfreund.tools/g' /etc/nginx/sites-available/juzi   # use your real domain
sudo ln -sf /etc/nginx/sites-available/juzi /etc/nginx/sites-enabled/juzi
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 8. First release + TLS

Easiest: configure GitHub secrets (below), push to `main`, and let Actions sync the SPA and run `deploy/deploy.sh`.

After the first release, run `sudo systemctl enable --now juzi` and `sudo certbot --nginx -d YOUR_DOMAIN` on the droplet. These one-time bootstrap steps are required for both the Actions and manual paths.

Manual (from a machine that can build the frontend):

```bash
cd frontend && npm ci && npm run build && cd ..
# Same caveat as CI: --delete before restart can briefly 404 hashed SPA assets
# under WhiteNoise (DEBUG=false). Future: stage + swap after workers restart.
rsync -az --delete frontend/dist/ juzi@YOUR_DROPLET:/var/www/juzi/frontend/dist/
ssh juzi@YOUR_DROPLET 'bash /var/www/juzi/deploy/deploy.sh'
sudo systemctl enable --now juzi   # on the droplet, if not already
sudo certbot --nginx -d YOUR_DOMAIN
```

Confirm:

- `https://YOUR_DOMAIN/api/health/`
- SPA loads at `https://YOUR_DOMAIN/`

Certbot renews via the packaged timer (`systemctl status certbot.timer`).

## Ongoing deploys

Push to `main`. After CI passes, Actions:

1. Uploads the Vite build artifact from the `frontend` job
2. `rsync --delete`s `frontend/dist` onto the droplet
3. SSHs in and runs `deploy/deploy.sh` (git pull, `uv sync`, migrate, collectstatic, restart)
Manual release (SPA already synced):

```bash
sudo -u juzi -H bash /var/www/juzi/deploy/deploy.sh
```

## GitHub Actions secrets

Create a GitHub Environment named **`production`** (referenced by the deploy job), then add these secrets:

| Secret | Purpose |
| --- | --- |
| `DROPLET_HOST` | Droplet IP or hostname |
| `DROPLET_USER` | SSH user (`juzi`) |
| `DROPLET_SSH_KEY` | Private key Actions uses to SSH into the droplet |

That CD key is **not** the GitHub deploy key from section 6. Generate a second keypair (on your laptop is fine), put the **private** half in `DROPLET_SSH_KEY`, and install the **public** half on the droplet:

```bash
# After generating the CD keypair locally, on the droplet:
sudo -u juzi -H tee -a /home/juzi/.ssh/authorized_keys < cd_key.pub
sudo -u juzi -H chmod 600 /home/juzi/.ssh/authorized_keys
```

`juzi` must be able to write `/var/www/juzi/frontend/dist`, `git fetch` via the section 6 deploy key, and `sudo systemctl restart juzi` via the sudoers rule above.

System users often have `/usr/sbin/nologin`. If Actions fails with "This account is currently not available", give `juzi` a shell:

```bash
sudo usermod -s /bin/bash juzi
```

## Templates in this directory

| File | Role |
| --- | --- |
| `juzi.service` | systemd unit for gunicorn |
| `nginx-juzi.conf` | HTTP reverse proxy (certbot adds SSL) |
| `deploy.sh` | pull → sync → migrate → collectstatic → restart (expects `frontend/dist` already present) |

## Error and performance monitoring

See [Sentry setup and verification](sentry.md) for project DSNs, CI secrets,
droplet configuration, slowdown alerts, and live acceptance checks.
