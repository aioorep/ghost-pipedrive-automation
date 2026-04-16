import os, hmac, hashlib, logging
from datetime import datetime
from flask import Flask, request, jsonify
import requests

PIPEDRIVE_API_TOKEN = os.environ["PIPEDRIVE_API_TOKEN"]
PIPEDRIVE_DOMAIN = os.environ["PIPEDRIVE_DOMAIN"]
GHOST_WEBHOOK_SECRET = os.environ.get("GHOST_WEBHOOK_SECRET", "")
PIPEDRIVE_BASE = f"https://{PIPEDRIVE_DOMAIN}.pipedrive.com/api/v1"
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
app = Flask(__name__)

PIPELINE_MAP = {"US":(2,8),"Middle East":(3,13),"Africa":(4,18),"Europe":(5,23),"Default":(1,1)}
MIDDLE_EAST_CODES = {"AE","SA","QA","KW","BH","OM","JO","LB","IQ","IR","YE","SY","PS","IL","TR"}
AFRICA_CODES = {"DZ","AO","BJ","BW","BF","BI","CM","CV","CF","TD","KM","CG","CD","CI","DJ","EG","GQ","ER","SZ","ET","GA","GM","GH","GN","GW","KE","LS","LR","LY","MG","MW","ML","MR","MU","MA","MZ","NA","NE","NG","RW","ST","SN","SL","SO","ZA","SS","SD","TZ","TG","TN","UG","ZM","ZW"}
EUROPE_CODES = {"AL","AD","AT","BY","BE","BA","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IS","IE","IT","LV","LI","LT","LU","MT","MD","MC","ME","NL","MK","NO","PL","PT","RO","RU","SM","RS","SK","SI","ES","SE","CH","UA","GB","VA"}

def get_pipeline_for_country(c):
    c = (c or "").upper()
    if c == "US": return PIPELINE_MAP["US"]
    if c in MIDDLE_EAST_CODES: return PIPELINE_MAP["Middle East"]
    if c in AFRICA_CODES: return PIPELINE_MAP["Africa"]
    if c in EUROPE_CODES: return PIPELINE_MAP["Europe"]
    return PIPELINE_MAP["Default"]

def region_label(c):
    c = (c or "").upper()
    if c == "US": return "US"
    if c in MIDDLE_EAST_CODES: return "Middle East"
    if c in AFRICA_CODES: return "Africa"
    if c in EUROPE_CODES: return "Europe"
    return "Global"

def _pd(p): return f"{PIPEDRIVE_BASE}{p}"
def _params(): return {"api_token": PIPEDRIVE_API_TOKEN}

def create_person(name, email):
    r = requests.post(_pd("/persons"), json={"name": name or email, "email": [{"value": email, "primary": True}]}, params=_params(), timeout=10)
    r.raise_for_status()
    return r.json()["data"]["id"]

def create_deal(title, person_id, pipeline_id, stage_id):
    r = requests.post(_pd("/deals"), json={"title": title, "person_id": person_id, "pipeline_id": pipeline_id, "stage_id": stage_id, "status": "open"}, params=_params(), timeout=10)
    r.raise_for_status()
    return r.json()["data"]["id"]

def add_note(deal_id, email, sub_at, cc, cn, region):
    geo = f"<b>Location:</b> {cn or cc} ({region})<br>" if (cn or cc) else ""
    content = f"<b>New Ghost Subscriber</b><br><b>Email:</b> {email}<br><b>Date:</b> {sub_at}<br>{geo}<b>Source:</b> Knowledge Base (Ghost Blog)<br><b>Pipeline:</b> {region}"
    requests.post(_pd("/notes"), json={"content": content, "deal_id": deal_id, "pinned_to_deal_flag": 1}, params=_params(), timeout=10)

@app.route("/webhook/ghost-subscriber", methods=["POST"])
def ghost_subscriber():
    data = request.get_json(silent=True) or {}
    # Supporte member.added ET subscriber.added
    member = (data.get("member") or data.get("subscriber") or {}).get("current", {})
    email = member.get("email", "").strip()
    name = member.get("name", "").strip()
    geo = member.get("geolocation") or {}
    country_code = geo.get("country_code", "")
    country_name = geo.get("country", "")
    created_at = member.get("created_at", datetime.utcnow().isoformat())
    if not email: return jsonify({"error": "no email"}), 400
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        sub_at = dt.strftime("%d/%m/%Y %H:%M UTC")
    except: sub_at = created_at
    pipeline_id, stage_id = get_pipeline_for_country(country_code)
    region = region_label(country_code)
    try:
        pid = create_person(name, email)
        did = create_deal(f"Ghost Subscriber - {name or email} [{region}]", pid, pipeline_id, stage_id)
        add_note(did, email, sub_at, country_code, country_name, region)
    except requests.HTTPError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"success": True, "deal_id": did, "pipeline": region}), 200

@app.route("/health")
def health(): return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
