# Motivation Caller — Web UI

A small web form: enter **phone number, name, and role** (CA, Engineer, Doctor…), click **Call now**,
and the deployed LiveKit agent (`motivation-caller`) phones that number and speaks a Hindi
motivational message about becoming that role.

The UI only dispatches the call. The agent itself already runs on LiveKit Cloud, so this
server just needs the LiveKit project keys.

## Files
- `server.py` — FastAPI app: serves the form and dispatches the call.
- `.env` — LiveKit keys + access password (never commit; already gitignored).
- `requirements.txt`, `Dockerfile`.

## Run locally
```bash
cd webui
uv venv .venv && uv pip install -r requirements.txt --python .venv
# .env must have LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET / ACCESS_TOKEN
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8080
```
Open http://localhost:8080, enter the access password, and place a call.

---

## Deploy on a GCP VM

### 1. Create the VM (from your machine, with gcloud)
```bash
gcloud compute instances create motivation-ui \
  --machine-type=e2-small \
  --image-family=debian-12 --image-project=debian-cloud \
  --zone=asia-south1-a \
  --tags=motivation-ui
```

### 2. Open port 8080 to the internet (or restrict to your IP with --source-ranges)
```bash
gcloud compute firewall-rules create allow-motivation-ui \
  --allow=tcp:8080 --target-tags=motivation-ui --source-ranges=0.0.0.0/0
```

### 3. Copy the app to the VM
```bash
gcloud compute scp --recurse ~/motivation-caller/webui motivation-ui:~/webui --zone=asia-south1-a
```

### 4. On the VM: install and run
```bash
gcloud compute ssh motivation-ui --zone=asia-south1-a
# --- now on the VM ---
sudo apt-get update && sudo apt-get install -y python3-pip python3-venv
cd ~/webui
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# make sure ~/webui/.env has the LiveKit keys and ACCESS_TOKEN (scp copied it)
```

### 5. Run it as a service so it stays up
```bash
sudo tee /etc/systemd/system/motivation-ui.service >/dev/null <<'UNIT'
[Unit]
Description=Motivation Caller UI
After=network.target

[Service]
User=%i
WorkingDirectory=/home/YOURUSER/webui
ExecStart=/home/YOURUSER/webui/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
UNIT
# replace YOURUSER with `whoami`, then:
sudo sed -i "s/YOURUSER/$(whoami)/g; s/%i/$(whoami)/" /etc/systemd/system/motivation-ui.service
sudo systemctl daemon-reload
sudo systemctl enable --now motivation-ui
sudo systemctl status motivation-ui
```

### 6. Open it
`http://<VM_EXTERNAL_IP>:8080` — enter the access password, fill the form, click Call.
Find the IP with:
```bash
gcloud compute instances describe motivation-ui --zone=asia-south1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

---

## Docker alternative
```bash
cd webui
docker build -t motivation-ui .
docker run -d --env-file .env -p 8080:8080 --restart unless-stopped motivation-ui
```

## Security notes
- `ACCESS_TOKEN` in `.env` is the form password — set a strong one. Leave it blank only if
  the VM is not reachable publicly.
- Prefer restricting the firewall `--source-ranges` to your own IP.
- For a real domain + HTTPS, put Caddy or nginx in front; browsers and callers don't need HTTPS
  for this to work, but a password over plain HTTP is visible on the network.
- This calls real phone numbers and costs money (Twilio). Only call people who expect it.
