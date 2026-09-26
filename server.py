"""Web UI to place motivational calls through the deployed LiveKit agent.

Enter a phone number, name and role (CA, Engineer, Doctor...), click Call, and the
LiveKit cloud agent (dispatch name "motivation-caller") phones that number and speaks
a Hindi motivational message about becoming that role.

Run:
    uv run uvicorn server:app --host 0.0.0.0 --port 8080

Environment (put in .env next to this file):
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET   # same project as the agent
    ACCESS_TOKEN                                        # shared password for the form
    AGENT_NAME=motivation-caller                        # optional, matches the deployed agent
"""

import json
import os
import re
import secrets

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from livekit import api

load_dotenv()

AGENT_NAME = os.getenv("AGENT_NAME", "motivation-caller")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")

for var in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
    if not os.getenv(var):
        raise RuntimeError(f"{var} is not set (see .env)")

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
app = FastAPI(title="Motivation Caller")


def normalize(phone: str) -> str:
    phone = re.sub(r"[\s\-()]", "", phone.strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not E164.match(phone):
        raise HTTPException(400, "Enter a full number with country code, e.g. +919876543210")
    return phone


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Motivation Caller</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0;
         min-height: 100vh; display: grid; place-items: center;
         background: linear-gradient(160deg, #0b1220, #121a2e); color: #eef3fb; padding: 24px; }
  .card { width: 100%; max-width: 440px; background: rgba(255,255,255,.04);
          border: 1px solid rgba(255,255,255,.08); border-radius: 20px; padding: 28px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  p.sub { margin: 0 0 22px; color: #9fb0cc; font-size: 14px; }
  label { display: block; font-size: 13px; color: #9fb0cc; margin: 14px 0 6px; }
  input, textarea { width: 100%; padding: 12px 14px; border-radius: 12px;
          border: 1px solid rgba(255,255,255,.14); background: rgba(0,0,0,.25);
          color: #eef3fb; font-size: 15px; font-family: inherit; }
  textarea { min-height: 110px; resize: vertical; }
  button { width: 100%; margin-top: 22px; padding: 14px; border: 0; border-radius: 12px;
          font-size: 16px; font-weight: 700; cursor: pointer; color: #06121f;
          background: linear-gradient(90deg, #38e1c6, #4f9cff); }
  button:disabled { opacity: .6; cursor: default; }
  #status { margin-top: 16px; font-size: 14px; min-height: 20px; }
  .ok { color: #7ff0c8; } .err { color: #ff8f8f; }
</style>
</head>
<body>
  <div class="card">
    <h1>Motivation Caller</h1>
    <p class="sub">Enter a number, name and role. The AI voice will call and motivate them toward that goal, in Hindi.</p>
    <form id="f">
      __TOKEN_FIELD__
      <label>Phone number (with country code)</label>
      <input name="phone" placeholder="+919876543210" required>
      <label>Name</label>
      <input name="name" placeholder="Bhoomi" required>
      <label>Role / goal to become</label>
      <input name="role" list="roles" placeholder="CA, Engineer, Doctor..." required>
      <datalist id="roles">
        <option value="CA"><option value="Engineer"><option value="Doctor">
        <option value="Lawyer"><option value="Teacher"><option value="IAS Officer">
        <option value="Pilot"><option value="Scientist"><option value="Designer">
        <option value="Developer"><option value="Entrepreneur"><option value="Nurse">
        <option value="Architect"><option value="Banker">
      </datalist>
      <button type="button" id="callbtn">Call now</button>
    </form>
    <div id="status"></div>
  </div>
<script>
const f = document.getElementById('f'), s = document.getElementById('status'), btn = document.getElementById('callbtn');
async function placeCall() {
  if (!f.reportValidity()) return;
  btn.disabled = true; s.className = ''; s.textContent = 'Placing call...';
  try {
    const res = await fetch('/call', { method: 'POST', body: new FormData(f) });
    let data = {};
    try { data = await res.json(); } catch (e) {}
    if (res.ok) { s.className = 'ok'; s.textContent = 'Calling ' + (data.phone || '') + ' ✓'; }
    else { s.className = 'err'; s.textContent = data.detail || ('Failed (' + res.status + ')'); }
  } catch (err) { s.className = 'err'; s.textContent = 'Could not reach the server: ' + err.message; }
  btn.disabled = false;
}
btn.addEventListener('click', placeCall);
// Enter key submits without a native (page-navigating) form post
f.addEventListener('submit', (e) => { e.preventDefault(); placeCall(); });
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    token_field = (
        '<label>Access password</label><input name="token" type="password" required>'
        if ACCESS_TOKEN
        else ""
    )
    return PAGE.replace("__TOKEN_FIELD__", token_field)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/call")
async def call(
    phone: str = Form(...),
    name: str = Form("friend"),
    role: str = Form(...),
    token: str = Form(""),
) -> JSONResponse:
    if ACCESS_TOKEN and not secrets.compare_digest(token, ACCESS_TOKEN):
        raise HTTPException(401, "Wrong access password")

    phone = normalize(phone)
    role = role.strip()
    if not role:
        raise HTTPException(400, "Role cannot be empty")

    room = f"call-{phone.lstrip('+')}-{secrets.token_hex(3)}"
    meta = {"phone": phone, "name": name.strip() or "friend", "role": role}

    async with api.LiveKitAPI() as lk:
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME, room=room, metadata=json.dumps(meta)
            )
        )
    return JSONResponse({"phone": phone, "room": room})
