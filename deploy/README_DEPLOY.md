# Deploying Softwar_application (Gunicorn + Nginx)

This document contains templated files and the exact commands to run to make the Django app run as a persistent service (systemd) and fronted by Nginx. Edit the files in `deploy/` and replace placeholders before copying them to system locations.

Files added:
- `deploy/gunicorn.service` — systemd unit template for Gunicorn
- `deploy/nginx_broker_portal.conf` — Nginx site template

Quick checklist (what this will achieve)
- Gunicorn runs as a systemd service and restarts automatically on boot/failure.
- Nginx reverse-proxies requests to Gunicorn and serves static files.

Before you start
- Ensure your virtualenv is at `/root/Broker_portal/Softwar_application/myenv` or update the `PATH` in the service file.
- Ensure `WorkingDirectory` points to `/root/Broker_portal/Softwar_application` (update if different).
- Replace `REPLACE_WITH_YOUR_USER` in `gunicorn.service` with a non-root user if possible.
- Replace `REPLACE_WITH_YOUR_DOMAIN_OR_IP` in `nginx_broker_portal.conf`.

Commands to run (as sudo where shown)

1) Activate virtualenv and install Gunicorn (run as the project user):

```bash
source myenv/bin/activate
pip install gunicorn
deactivate
```

2) Copy the systemd unit to `/etc/systemd/system/` (run as root):

```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/gunicorn-broker_portal.service
# Edit the file to replace placeholders, then reload systemd
sudo systemctl daemon-reload
sudo systemctl enable gunicorn-broker_portal
sudo systemctl start gunicorn-broker_portal
sudo systemctl status gunicorn-broker_portal
```

3) Copy the Nginx site file and enable it:

```bash
sudo cp deploy/nginx_broker_portal.conf /etc/nginx/sites-available/broker_portal
sudo ln -s /etc/nginx/sites-available/broker_portal /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

4) Collect static files (run as project user):

```bash
source myenv/bin/activate
python manage.py collectstatic --noinput
deactivate
```

5) Firewall (UFW example)

```bash
sudo ufw allow 'Nginx Full'
sudo ufw status
```

6) (Optional) Obtain HTTPS cert with Certbot (requires a domain pointed at your IP):

```bash
sudo certbot --nginx -d yourdomain.example
```

Troubleshooting
- If `systemctl status` shows permission errors, double-check `User` in the service file and file/directory permissions.
- If Nginx shows 502 Bad Gateway, ensure Gunicorn is running and the socket path `/run/gunicorn-broker_portal.sock` exists and is readable by the `www-data` group (or adjust socket ownership in systemd unit).

Alternative quick options (if you can't use systemd or don't have sudo)
- Use tmux/screen to run `gunicorn` in the background (not auto-start on reboot).
- Use a process supervisor like `supervisord` if preferred.

If you want, I can:
- Replace placeholders in the templates for you (if you tell me the user name and domain/IP).
- Attempt to install Gunicorn and start the service now (I'll run the commands here). Note: I will need sudo for system-level actions.
