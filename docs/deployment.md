# Deploying ETIKE to a server

## Go-live checklist

Tick every line before sharing the link. Each one points to the step below that does it.

- [ ] Ubuntu VPS running, domain's DNS A record points at it, SSH keys only, firewall on (step 1)
- [ ] `.env` filled in: random secrets, `FLASK_ENV=production`, `DEMO_LOGIN=false`, `FEATURE_BUS_BOOKING=false`, `CORS_ORIGINS` empty (step 2)
- [ ] Stack up, `db upgrade` done, `/api/health` says ok (step 3)
- [ ] Admin account created; `ADMIN_*` lines removed from `.env` (step 4)
- [ ] HTTPS on: `NGINX_CONF=https.conf`, `http://` redirects, SSL Labs grade A (step 6)
- [ ] `MOMO_CALLBACK_URL=https://YOUR_DOMAIN/api/payments/callback` (step 5)
- [ ] GitHub secrets set; a push to `main` deploys (step 7)
- [ ] Cron: `expire-bookings` every minute and the nightly backup (steps 8 and 9)
- [ ] One backup restored into a scratch database (step 9)
- [ ] Real districts and routes loaded; drivers' documents checked and drivers approved (step 10)
- [ ] The required documents list in `backend/app/driver_documents.py` confirmed with RURA (step 10)
- [ ] Logged in as a passenger on a phone: searched, booked a ride, cancelled it (step 10)
- [ ] The live link is in the main README

## What this sets up

This sets up one Ubuntu VPS running the production stack (`docker-compose.prod.yml`): Nginx, the Flask API on Gunicorn, and PostgreSQL. The same steps work for staging and production; use a separate server (or folder and `.env`) for each.

## 1. Prepare the server

1. Create an Ubuntu 24.04 VPS with at least 1 GB RAM (the cheapest plan of most providers, about 5 USD a month, is enough). Point your domain's DNS A record at its IP address.
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
5. Install Docker Engine and the Compose plugin from Docker's own repository (https://docs.docker.com/engine/install/ubuntu/):
   ```bash
   sudo apt update && sudo apt install -y ca-certificates curl git
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
     | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   sudo usermod -aG docker deploy
   ```
   Log out and in again as `deploy`, then check: `docker compose version`.
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
- `DEMO_LOGIN=false`, `FEATURE_BUS_BOOKING=false`, and leave `CORS_ORIGINS` empty: the pages and the API share one domain, so no other site needs access.
- Replace every `change-me`. Make `SECRET_KEY` and `JWT_SECRET_KEY` two **different** random values:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`
- Make `DATABASE_URL` match `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`.
- Payments (optional, see "MTN MoMo payments" below): the `MOMO_*` variables.
- SMS (optional, see the main README): `AT_USERNAME`, `AT_API_KEY`.

`.env` never goes into Git. The full list of variables is in the main [README](../README.md#environment-variables).

## 3. Start it

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api flask --app wsgi db upgrade
docker compose -f docker-compose.prod.yml ps        # all three should become "healthy"
curl http://localhost/api/health                    # {"database": "ok", "status": "ok"}
```

What production adds over local development:

- Gunicorn (worker count from `GUNICORN_WORKERS`), never the Flask debug server. `FLASK_ENV=production` keeps debug off. The API refuses to start if `DATABASE_URL`, `SECRET_KEY` or `JWT_SECRET_KEY` is missing, if a secret is still `change-me` or shorter than 32 characters, if the two secrets are the same, or if `DEMO_LOGIN` is on. If `ps` shows the API restarting, `docker compose -f docker-compose.prod.yml logs api` says which.
- `restart: unless-stopped` on every container, so they come back after a crash or reboot.
- Health checks: the API checks `/api/health`, and Nginx only starts once the API is healthy.
- The API runs as a normal user inside its container, not root.

## 4. Create the first admin

There are no built-in admin accounts. Create one on the server:

```bash
docker compose -f docker-compose.prod.yml exec api flask --app wsgi create-admin
```

It asks for a name, phone number and password (at least 12 characters). Then log in on the website with that phone number; admins land on the Drivers page, where they approve drivers and verify bus companies.

## 5. MTN MoMo payments

### Which sandbox we use

We test on MTN's **global** sandbox: portal https://momodeveloper.mtn.com, API address `https://sandbox.momodeveloper.mtn.com`.

MTN Rwanda has its own portal (https://momodeveloper.mtn.co.rw, API address `https://sandbox.momodeveloper.mtn.co.rw`), but on 16 November 2026 its sandbox failed on MTN's side: with a valid, active Collections key, `POST /v1_0/apiuser` answered `404 Resource not found` and `POST /collection/token/` never answered. Keys from one portal do not work on the other (the wrong one answers 401).

Production will use the Rwanda host with Rwanda live keys (see "Going live" below).

### Sandbox set-up

1. Sign up at https://momodeveloper.mtn.com and subscribe to the **Collections** product. Your profile page shows its primary and secondary keys.
2. In `.env` on the server:
   ```
   MOMO_BASE_URL=https://sandbox.momodeveloper.mtn.com
   MOMO_TARGET_ENVIRONMENT=sandbox
   MOMO_SUBSCRIPTION_KEY=the Collections primary key
   MOMO_CURRENCY=EUR
   ```
3. Restart, then create the sandbox API user and key. The callback host must be the domain MoMo will call:
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   docker compose -f docker-compose.prod.yml exec api flask --app wsgi momo-create-user --callback-host YOUR_DOMAIN
   ```
   Put the two lines it prints (`MOMO_API_USER`, `MOMO_API_KEY`) in `.env` and restart again.
4. Once HTTPS is on (step 6), set `MOMO_CALLBACK_URL=https://YOUR_DOMAIN/api/payments/callback` and restart. MoMo calls it when a payment finishes, so the booking is confirmed even if the passenger closes the payment page (the page also checks the status itself). It must be the live `https://` domain: MoMo cannot reach `localhost`. We have not yet tested the callback against a live URL: if a request to pay is refused with it set, remove it and tell the team.

Note: rides are paid to the driver, so MoMo is only used by bus tickets, which are off (`FEATURE_BUS_BOOKING=false`). To test MoMo on the server, switch the bus flag on for the test only.

If MoMo answers "Access denied due to invalid subscription key", the key is from the other portal, the Collections subscription is not active, or the key was regenerated.

### Currency

The sandbox accepts **EUR only**. We checked on 16 November 2026: a request to pay in RWF (and in USD) is refused with `INVALID_CURRENCY: Currency not supported`, and the same request in EUR succeeds. So in the sandbox `MOMO_CURRENCY=EUR`, the booking's amount in francs is sent as the same number of euros, and the payment page shows a "Sandbox test currency" note. No real money moves.

### MoMo sandbox test numbers

In the sandbox no phone rings. The payer number decides what happens. These are the answers we got from the global sandbox on 16 November 2026:

| Payer number | Status from MoMo | What ETIKE does |
|--------------|------------------|-----------------|
| Any normal number, e.g. `0781234567` | `SUCCESSFUL` at once | Booking confirmed |
| `46733123450` | `FAILED`, reason `INTERNAL_PROCESSING_ERROR` | Booking cancelled, seats returned, "Payment didn't go through" |
| `46733123451` | `FAILED`, reason `APPROVAL_REJECTED` | Booking cancelled, seats returned, "Payment declined" |
| `46733123452` | `FAILED`, reason `EXPIRED` | Booking cancelled, seats returned, "Payment not approved in time" |
| `46733123453` | `PENDING` (stayed pending for the 40 seconds we watched) | Keeps waiting; the booking expires after the 15-minute hold |
| `46733123454` | `CREATED`, then `SUCCESSFUL` a few seconds later | Waits, then booking confirmed |

While `MOMO_TARGET_ENVIRONMENT=sandbox`, the payment page accepts these test numbers as well as MTN Rwanda numbers (078, 079). In production only MTN Rwanda numbers are accepted.

### Going live

Production needs a MoMo business account approved by MTN Rwanda (KYC). MTN then gives you the live subscription key, API user and API key. Set `MOMO_BASE_URL` to the live Rwanda address MTN gives you, `MOMO_TARGET_ENVIRONMENT=mtnrwanda` and `MOMO_CURRENCY=RWF`. `flask momo-create-user` is for the sandbox only. Make one small real payment before opening to the public: the live service has not been tested.

## 6. Turn on HTTPS (Let's Encrypt)

1. With the stack running on port 80:
   ```bash
   sudo apt install certbot
   sudo mkdir -p /var/www/certbot
   sudo certbot certonly --webroot -w /var/www/certbot -d YOUR_DOMAIN
   ```
2. `cp nginx/https.conf.example nginx/https.conf` and replace `YOUR_DOMAIN` (four places): `sed -i 's/YOUR_DOMAIN/etike.example.com/g' nginx/https.conf`. Git ignores `nginx/https.conf`, so deploys never overwrite it.
3. Add `NGINX_CONF=https.conf` to `.env`, then recreate Nginx:
   `docker compose -f docker-compose.prod.yml up -d --force-recreate nginx`
4. Certbot renews certificates by itself. Reload Nginx after each renewal:
   ```bash
   sudo certbot renew --deploy-hook "docker compose -f /home/deploy/etike/docker-compose.prod.yml exec nginx nginx -s reload"
   ```
   (run once by hand; Certbot remembers the hook).
5. Check: `https://YOUR_DOMAIN` loads, `http://` redirects to it, and https://www.ssllabs.com/ssltest/ gives an A.

The HTTPS config adds HSTS on top of the headers Nginx always sends (Content Security Policy, no framing, no MIME sniffing, strict referrer). Both configs limit `/api/auth/` (login and sign-up) to 10 requests a minute per IP address, answering 429 beyond that.

## 7. Automatic deploys from GitHub

`.github/workflows/deploy.yml` runs on every push to `main`: it SSHes in, runs `git pull`, rebuilds, and applies migrations (`flask db upgrade`). Until these GitHub secrets exist it skips itself instead of failing:

| Secret | Value |
|--------|-------|
| `STAGING_HOST` | Server IP or domain |
| `STAGING_USER` | `deploy` |
| `STAGING_SSH_KEY` | Private half of a new key pair made only for deploys; add the public half to `~/.ssh/authorized_keys` on the server |

## 8. Background job: expire unpaid bookings

Unpaid bookings are also released whenever someone searches or books, but run the release every minute too, so seats come back even when the site is quiet:

```bash
crontab -e
* * * * * cd /home/deploy/etike && docker compose -f docker-compose.prod.yml exec -T api flask --app wsgi expire-bookings > /dev/null
```

## 9. Backups

`infra/backups/backup-db.sh` saves a compressed `pg_dump` named `etike-YYYY-MM-DD.sql.gz` in `~/backups` and keeps the newest 7. Add it to cron (every night at 02:30):

```bash
mkdir -p ~/backups
crontab -e
30 2 * * * /home/deploy/etike/infra/backups/backup-db.sh >> /home/deploy/backups/backup.log 2>&1
```

The script backs up the database. Files live in two Docker volumes; back them up too, for example weekly:

- `uploads`: car photos;
- `documents`: drivers' legal documents (ID, licence, RURA, insurance…), personal data.

```bash
docker run --rm -v etike_uploads:/data -v ~/backups:/backup alpine tar czf /backup/uploads-$(date +%F).tar.gz -C /data .
docker run --rm -v etike_documents:/data -v ~/backups:/backup alpine tar czf /backup/documents-$(date +%F).tar.gz -C /data .
chmod 600 ~/backups/documents-*.tar.gz
```

(The volume is named after the project folder; check with `docker volume ls`.)

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

## 10. Real data and a first check

From the server, after the admin exists:

```bash
# Districts and routes collected by the team (see data/README.md)
docker compose -f docker-compose.prod.yml run --rm -v "$PWD/data:/data" api python /data/scripts/clean_data.py
docker compose -f docker-compose.prod.yml run --rm -v "$PWD/data:/data" api python /data/scripts/load_data.py
# Real drivers who gave consent (CSV copied to data/raw/ on the server, never committed)
docker compose -f docker-compose.prod.yml run --rm -v "$PWD/data:/data" api python /data/scripts/add_drivers.py /data/raw/drivers.csv
```

Each driver logs in, fills in their details (national ID number, date of birth, gender, home, licence number) and uploads their six documents on the driver page (national ID, driving licence, RURA authorisation, vehicle registration card, insurance, inspection certificate). On the admin Drivers page, open each one and check it against the details the driver typed in and their car plate; **Approve** only unlocks when all six are uploaded and in date. Reject with a reason if something is wrong: the driver sees it and can upload a corrected document.

The list of required documents is in `backend/app/driver_documents.py`. It follows RURA's rule that carrying paying passengers needs its authorisation, but confirm the exact list with RURA before going live. Never run `local_test_data.py` on the server: it is fake data for laptops only, and it is not in Git or in the server image.

Then, on a phone: sign up as a passenger, search a real route, book a ride, cancel it.

## 11. Security checklist

- [ ] `.env` has `chmod 600`, real random secrets, and is not in Git.
- [ ] MoMo stays on the sandbox (`MOMO_TARGET_ENVIRONMENT=sandbox`) until MTN approves the live account.
- [ ] `CORS_ORIGINS` is empty unless another site must call the API.
- [ ] `DEMO_LOGIN` is not `true` (it logs in to test accounts without a password).
- [ ] Only ports 22, 80 and 443 are open; SSH keys only, no root login.
- [ ] HTTPS is on and SSL Labs gives an A.
- [ ] The admin password is long and stored in a password manager; `ADMIN_*` values are removed from `.env` after `create-admin`.
- [ ] Backups run nightly and a restore has been tested.
- [ ] Driver documents are only in the `documents` volume (never in Git or `/uploads`), and their backups are `chmod 600`.
