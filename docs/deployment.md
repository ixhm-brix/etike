# Deploying ETIKE to a server

This sets up one Ubuntu VPS running the production stack (`docker-compose.prod.yml`): Nginx, the Flask API on Gunicorn, and PostgreSQL. The same steps work for staging and production; use a separate server (or folder and `.env`) for each.

## 1. Prepare the server

1. Create an Ubuntu 24.04 VPS with at least 1 GB RAM. Point your domain's DNS A record at its IP address.
2. Log in as root once, create a deploy user and give it your SSH key:
   ```bash
   adduser deploy
   usermod -aG sudo deploy
   rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
   ```
3. Turn off password logins: in `/etc/ssh/sshd_config` set `PasswordAuthentication no` and `PermitRootLogin no`, then `systemctl restart ssh`.
4. Firewall: allow only SSH and web traffic.
   ```bash
   ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable
   ```
5. Install Docker Engine and the Compose plugin: https://docs.docker.com/engine/install/ubuntu/. Then `usermod -aG docker deploy` and log in again as `deploy`.
6. Turn on automatic security updates: `sudo apt install unattended-upgrades`.

## 2. Get the code and settings

```bash
git clone https://github.com/ixhm-brix/etike.git ~/etike
cd ~/etike
cp .env.example .env
chmod 600 .env
nano .env
```

In `.env`:

- `FLASK_ENV=production`
- Replace every `change-me`. Make `SECRET_KEY` and `JWT_SECRET_KEY` two **different** random values:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`
- Make `DATABASE_URL` match `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`.
- Payments and SMS (optional, see the main README): `FLW_SECRET_KEY`, `FLW_SECRET_HASH`, `FLW_REDIRECT_URL=https://YOUR_DOMAIN/payment.html`, `AT_USERNAME`, `AT_API_KEY`.

`.env` never goes into Git. The full list of variables is in the main [README](../README.md#environment-variables).

## 3. Start it

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api flask --app wsgi db upgrade
docker compose -f docker-compose.prod.yml ps        # all three should become "healthy"
curl http://localhost/api/health                    # {"database": "ok", "status": "ok"}
```

What production adds over local development:

- Gunicorn (worker count from `GUNICORN_WORKERS`), never the Flask debug server. `FLASK_ENV=production` keeps debug off, and the API refuses to start if `DATABASE_URL`, `SECRET_KEY` or `JWT_SECRET_KEY` is missing.
- `restart: unless-stopped` on every container, so they come back after a crash or reboot.
- Health checks: the API checks `/api/health`, and Nginx only starts once the API is healthy.
- The API runs as a normal user inside its container, not root.

## 4. Create the first admin

There are no built-in admin accounts. Create one on the server:

```bash
docker compose -f docker-compose.prod.yml exec api flask --app wsgi create-admin
```

It asks for a name, phone number and password (at least 12 characters). Then log in on the website with that phone number; admins land on the Drivers page, where they approve drivers and verify bus companies.

## 5. Turn on HTTPS (Let's Encrypt)

1. With the stack running on port 80:
   ```bash
   sudo apt install certbot
   sudo mkdir -p /var/www/certbot
   sudo certbot certonly --webroot -w /var/www/certbot -d YOUR_DOMAIN
   ```
2. `cp nginx/https.conf.example nginx/https.conf` and replace `YOUR_DOMAIN` (four places).
3. In `docker-compose.prod.yml`, change `./nginx/default.conf` to `./nginx/https.conf`, then:
   `docker compose -f docker-compose.prod.yml up -d`
4. Certbot renews certificates by itself. Reload Nginx after each renewal:
   ```bash
   sudo certbot renew --deploy-hook "docker compose -f /home/deploy/etike/docker-compose.prod.yml exec nginx nginx -s reload"
   ```
   (run once by hand; Certbot remembers the hook).
5. Check: `https://YOUR_DOMAIN` loads, `http://` redirects to it, and https://www.ssllabs.com/ssltest/ gives an A.

The HTTPS config adds HSTS on top of the headers Nginx always sends (Content Security Policy, no framing, no MIME sniffing, strict referrer). Both configs limit `/api/auth/` (login and sign-up) to 10 requests a minute per IP address, answering 429 beyond that.

## 6. Automatic deploys from GitHub

`.github/workflows/deploy.yml` runs on every push to `main`: it SSHes in, runs `git pull`, rebuilds, and applies migrations (`flask db upgrade`). Until these GitHub secrets exist it skips itself instead of failing:

| Secret | Value |
|--------|-------|
| `STAGING_HOST` | Server IP or domain |
| `STAGING_USER` | `deploy` |
| `STAGING_SSH_KEY` | Private half of a new key pair made only for deploys; add the public half to `~/.ssh/authorized_keys` on the server |

## 7. Background job: expire unpaid bookings

Unpaid bookings are also released whenever someone searches or books, but run the release every minute too, so seats come back even when the site is quiet:

```bash
crontab -e
* * * * * cd /home/deploy/etike && docker compose -f docker-compose.prod.yml exec -T api flask --app wsgi expire-bookings > /dev/null
```

## 8. Backups

`infra/backups/backup-db.sh` saves a compressed `pg_dump` named `etike-YYYY-MM-DD.sql.gz` in `~/backups` and keeps the newest 7. Add it to cron (every night at 02:30):

```bash
mkdir -p ~/backups
crontab -e
30 2 * * * /home/deploy/etike/infra/backups/backup-db.sh >> /home/deploy/backups/backup.log 2>&1
```

Backups contain personal data (names, phone numbers), so the folder is readable by the owner only. Also copy them off the server regularly (for example `scp` to a team laptop or an encrypted bucket): a backup on the same disk does not survive losing the server.

### Restoring a backup

1. Stop the API so nothing writes during the restore:
   `docker compose -f docker-compose.prod.yml stop api nginx`
2. Load the dump (it drops and recreates the tables):
   ```bash
   gunzip -c ~/backups/etike-2026-11-14.sql.gz \
     | docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
   ```
   (`source .env` first so the variables are set.)
3. Bring the migrations up to date and start again:
   ```bash
   docker compose -f docker-compose.prod.yml start api nginx
   docker compose -f docker-compose.prod.yml exec api flask --app wsgi db upgrade
   ```

Test a restore into a scratch database now and then; a backup you have never restored is a guess.

## 9. Security checklist

- [ ] `.env` has `chmod 600`, real random secrets, and is not in Git.
- [ ] Flutterwave keys are TEST keys until the team decides to go live.
- [ ] `CORS_ORIGINS` is empty unless another site must call the API.
- [ ] Only ports 22, 80 and 443 are open; SSH keys only, no root login.
- [ ] HTTPS is on and SSL Labs gives an A.
- [ ] The admin password is long and stored in a password manager; `ADMIN_*` values are removed from `.env` after `create-admin`.
- [ ] Backups run nightly and a restore has been tested.
