"""
NGO Intelligence Hub — Flask backend powered by AWS Bedrock.

Uses Amazon Nova models via AWS Bedrock as the primary AI provider,
with automatic fallback to OpenAI if Bedrock is unavailable.

Model routing:
  - Nova Pro:   Complex reasoning (copilot, insights, funding matching)
  - Nova Lite:  Standard tasks (email drafting, summarization)
  - Nova Micro: Fast tasks (briefings)

Endpoints:
  GET  /api/items              -> list[Item]
  GET  /api/items/<id>         -> Item
  GET  /api/briefing           -> { date, summary, highlights[] }
  POST /api/copilot            -> { reply }
  POST /api/copilot/draft-email -> { subject, body, suggested_recipients }
  GET  /api/insights           -> { insights[] }
  GET  /api/markers            -> list[Marker]
  POST /api/funding/search     -> { matches[] }
  GET  /api/meta               -> { topics[], regions[], typeLabels{} }
  GET  /api/search             -> list[Item]
  POST /api/send-email         -> { success, message }
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS

# Load environment from .env
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / "Python pipeline" / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
except ImportError:
    pass

from bedrock_client import chat  # AWS Bedrock + OpenAI fallback

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "items.json"
CLIENT_DIR = BASE_DIR / "dist" / "client"

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
CORS(app, supports_credentials=True)


# ---------- data loading -----------------------------------------------------

def load_items() -> list[dict]:
    """Load items from the exported JSON file."""
    if not DATA_FILE.exists():
        return []
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)


# Intent keyword groups -> item types they should surface
_INTENT_TYPE_MAP = {
    "funding": {"funding", "fund", "grant", "grants", "deadline", "deadlines",
                "money", "apply", "application", "eligibility", "award", "fellowship",
                "finance", "financing", "donor", "budget", "amount"},
    "news": {"news", "article", "articles", "headline", "headlines", "story",
             "report", "reports", "happening", "update", "updates"},
    "email": {"email", "emails", "alert", "alerts", "inbox", "message", "messages"},
}


def select_relevant_items(items: list[dict], question: str, history: list[dict],
                          max_items: int = 30) -> list[dict]:
    """
    Select the items most relevant to a user question for LLM context.

    Combines three signals so the chatbot always has useful context:
      1. Keyword overlap between the question (+ recent assistant turns) and item text.
      2. Intent detection: if the question is about funding/news/email, surface items
         of that type even when the literal words don't appear in the item text.
      3. A diverse fallback mix across all types so the model is never starved of context.
    """
    if not items:
        return []

    # Build keyword set from question and recent assistant messages
    keywords = {w.lower().strip(".,!?;:") for w in question.split() if len(w) > 2}
    for entry in history[-4:]:
        if entry.get("role") == "assistant":
            keywords.update(w.lower().strip(".,!?;:") for w in entry.get("content", "").split() if len(w) > 4)

    # Detect which item types the question is asking about
    q_lower = question.lower()
    intent_types = set()
    for item_type, trigger_words in _INTENT_TYPE_MAP.items():
        if trigger_words & keywords or any(t in q_lower for t in trigger_words):
            intent_types.add(item_type)

    priority_order = {"high": 0, "med": 1, "low": 2}

    def score(item: dict) -> tuple:
        searchable = " ".join([
            item.get("title", ""), item.get("translation", ""), item.get("summary", ""),
            " ".join(item.get("topic", [])), " ".join(item.get("region", [])),
        ]).lower()
        kw_hits = sum(1 for kw in keywords if kw and kw in searchable)
        type_hit = 1 if item.get("type") in intent_types else 0
        prio = priority_order.get(item.get("priority", "low"), 2)
        # Higher kw_hits and type_hit first; then higher priority; then newer
        return (-(kw_hits * 2 + type_hit * 3), prio, item.get("date", "") or "")

    # Items with any relevance signal
    relevant = [
        i for i in items
        if any(kw and kw in " ".join([
            i.get("title", ""), i.get("translation", ""), i.get("summary", ""),
            " ".join(i.get("topic", [])), " ".join(i.get("region", [])),
        ]).lower() for kw in keywords) or i.get("type") in intent_types
    ]

    selected = sorted(relevant, key=score)[:max_items]

    # If we still have few items, top up with a diverse, high-priority mix
    if len(selected) < max_items:
        selected_ids = {id(i) for i in selected}
        remaining = sorted(
            (i for i in items if id(i) not in selected_ids),
            key=lambda i: (priority_order.get(i.get("priority", "low"), 2), i.get("date", "") or ""),
        )
        selected.extend(remaining[: max_items - len(selected)])

    return selected


def _build_context_items(matched: list[dict]) -> list[dict]:
    """Build compact item dicts for the LLM context."""
    context_items = []
    for i in matched:
        entry = {
            "title": i.get("title", ""),
            "type": i.get("type", ""),
            "summary": (i.get("translation") or i.get("summary", ""))[:200],
        }
        if i.get("deadline"):
            entry["deadline"] = i["deadline"]
        if i.get("amount"):
            entry["amount"] = i["amount"]
        if i.get("link"):
            entry["link"] = i["link"]
        if i.get("region"):
            entry["region"] = i["region"]
        if i.get("topic"):
            entry["topic"] = i["topic"]
        if i.get("contact_email"):
            entry["contact_email"] = i["contact_email"]
        context_items.append(entry)
    return context_items


# ---------- API --------------------------------------------------------------

@app.get("/api/items")
def list_items():
    items = load_items()
    t = request.args.get("type")
    r = request.args.get("region")
    p = request.args.get("priority")
    if t:
        items = [i for i in items if i.get("type") == t]
    if r:
        items = [i for i in items if r in i.get("region", [])]
    if p:
        items = [i for i in items if i.get("priority") == p]
    return jsonify(items)


@app.get("/api/items/<item_id>")
def get_item(item_id: str):
    for i in load_items():
        if i.get("id") == item_id:
            return jsonify(i)
    abort(404)


@app.get("/api/briefing")
def briefing():
    items = load_items()
    high = [i for i in items if i.get("priority") == "high"]

    priority_order = {"high": 0, "med": 1, "low": 2}
    sorted_items = sorted(
        items,
        key=lambda i: (priority_order.get(i.get("priority", "low"), 2), i.get("date", "") or ""),
    )
    sorted_items.sort(key=lambda i: priority_order.get(i.get("priority", "low"), 2))

    top3 = sorted_items[:3]
    if top3:
        titles = ", ".join(i.get("title", "Untitled")[:60] for i in top3)
        summary_en = (
            f"{len(items)} items total. {len(high)} need attention. "
            f"Top items: {titles}."
        )
        summary_de = (
            f"{len(items)} Eintr\u00e4ge insgesamt. {len(high)} erfordern Aufmerksamkeit. "
            f"Wichtigste Eintr\u00e4ge: {titles}."
        )
    else:
        summary_en = "No items to review right now."
        summary_de = "Derzeit keine Eintr\u00e4ge zu pr\u00fcfen."

    return jsonify({
        "date": request.args.get("date"),
        "summary_en": summary_en,
        "summary_de": summary_de,
        "highlights": [
            {"id": i["id"], "title": i["title"], "summary": i["summary"],
             "title_de": i.get("title", ""), "summary_de": i.get("translation_de", i.get("summary", ""))}
            for i in high
        ],
        "stats": {"reviewed": len(items), "newOvernight": len(high)},
    })


@app.get("/api/search")
def search_items():
    """Simple case-insensitive substring search across all items."""
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify([])

    items = load_items()
    results = []
    for i in items:
        searchable = " ".join([
            i.get("title", ""), i.get("translation", ""), i.get("summary", ""),
            " ".join(i.get("topic", [])), " ".join(i.get("region", [])),
            i.get("source", ""),
        ]).lower()
        if q in searchable:
            results.append(i)
            if len(results) >= 20:
                break
    return jsonify(results)


@app.post("/api/copilot")
def copilot():
    """AI chatbot powered by AWS Bedrock (Amazon Nova Pro)."""
    payload = request.get_json(silent=True) or {}
    question = (payload.get("message") or "").strip()
    history = payload.get("history", [])
    if not question:
        return jsonify({"reply": "Ask me about deadlines, partners, or regions."})

    items = load_items()
    matched = select_relevant_items(items, question, history, max_items=30)
    context_items = _build_context_items(matched)

    # Build messages for Bedrock
    messages = [
        {"role": "system", "content": (
            "You are an assistant for an NGO press/funding monitoring tool called Lumen, "
            "powered by AWS Bedrock. Answer using ONLY the provided items. If the answer "
            "isn't in them, say so rather than guessing. Be concise. Mention source links "
            "where relevant.\n\nAvailable items:\n"
            + json.dumps(context_items, ensure_ascii=False)[:16000]
        )},
    ]
    for entry in history[-6:]:
        role = "assistant" if entry.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": entry.get("content", "")})
    messages.append({"role": "user", "content": question})

    try:
        reply = chat(messages, tier="pro", temperature=0.4, max_tokens=1024)
    except Exception as e:
        reply = f"Sorry, I couldn't process that right now. ({str(e)[:100]})"

    return jsonify({"reply": reply})


@app.post("/api/copilot/draft-email")
def copilot_draft_email():
    """Draft an email using AWS Bedrock (Amazon Nova Lite)."""
    payload = request.get_json(silent=True) or {}
    question = (payload.get("message") or "").strip()
    history = payload.get("history", [])
    language = (payload.get("language") or "en").strip().lower()
    if not question:
        return jsonify({"subject": "", "body": "", "suggested_recipients": [], "error": "No request provided."})

    items = load_items()
    matched = select_relevant_items(items, question, history, max_items=20)

    available_emails = []
    items_with_contact = []
    items_without_contact = []
    for i in matched:
        if i.get("contact_email"):
            available_emails.append(i["contact_email"])
            items_with_contact.append(i.get("title", "Unknown"))
        else:
            items_without_contact.append(i.get("title", "Unknown"))
    available_emails = list(set(available_emails))

    context_items = []
    for i in matched:
        entry = {"title": i.get("title", ""), "summary": (i.get("translation") or i.get("summary", ""))[:150]}
        if i.get("contact_email"):
            entry["contact_email"] = i["contact_email"]
        if i.get("deadline"):
            entry["deadline"] = i["deadline"]
        context_items.append(entry)

    contact_note = ""
    if items_without_contact:
        if available_emails:
            contact_note = f"Note: Only {len(items_with_contact)} of {len(matched)} relevant items have a contact email ({', '.join(available_emails)}). Items without contacts: {', '.join(items_without_contact[:5])}."
        else:
            contact_note = f"Note: None of the {len(matched)} relevant items have a contact email listed."

    lang_instruction = "Write the subject and body in German." if language == "de" else "Write the subject and body in English."
    system_msg = (
        f"Draft a professional, concise email based on the user's request and provided context. "
        f"{lang_instruction} Return JSON: {{\"subject\": \"...\", \"body\": \"...\", \"suggested_recipients\": [...]}}. "
        f"Only suggest recipients from the contact emails provided - never invent an address. "
        f"Available contact emails: {json.dumps(available_emails)}. {contact_note}"
    )

    messages = [{"role": "system", "content": system_msg}]
    for entry in history[-4:]:
        role = "assistant" if entry.get("role") == "assistant" else "user"
        messages.append({"role": role, "content": entry.get("content", "")})
    messages.append({"role": "user", "content": f"Request: {question}\n\nContext:\n{json.dumps(context_items, ensure_ascii=False)[:8000]}"})

    try:
        content = chat(messages, tier="lite", temperature=0.3, max_tokens=1024, json_mode=True)
        result = json.loads(content)
    except Exception as e:
        return jsonify({"subject": "", "body": "", "suggested_recipients": [], "error": f"Draft failed: {str(e)[:100]}"})

    reply = {
        "subject": result.get("subject", ""),
        "body": result.get("body", ""),
        "suggested_recipients": result.get("suggested_recipients", []),
    }
    if contact_note:
        reply["contact_note"] = contact_note
    return jsonify(reply)


@app.post("/api/send-email")
def send_email_route():
    """Send an email via SMTP. Only fires on explicit confirmed=true."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import time as _time

    payload = request.get_json(silent=True) or {}
    if payload.get("confirmed") is not True:
        return jsonify({"success": False, "error": "Sending requires explicit confirmation (confirmed: true)."}), 400

    to = payload.get("to", [])
    subject = payload.get("subject", "")
    body = payload.get("body", "")
    if not to or not subject or not body:
        return jsonify({"success": False, "error": "Missing required fields: to, subject, body."}), 400

    smtp_user = os.environ.get("GMAIL_IMAP_USER")
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD")

    if not smtp_user or not smtp_pass:
        return jsonify({"success": False, "error": "SMTP credentials not configured."}), 500

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to, msg.as_string())

        log_file = BASE_DIR / "data" / "sent_emails_log.json"
        log_file.parent.mkdir(exist_ok=True)
        log_entries = []
        if log_file.exists():
            try:
                log_entries = json.loads(log_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        log_entries.append({"to": to, "subject": subject, "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ")})
        log_file.write_text(json.dumps(log_entries, ensure_ascii=False, indent=2), encoding="utf-8")

        return jsonify({"success": True, "message": f"Email sent to {', '.join(to)}."})
    except Exception as e:
        return jsonify({"success": False, "error": f"SMTP error: {str(e)[:200]}"}), 500


@app.get("/api/insights")
def insights():
    """AI-detected partnership opportunities using AWS Bedrock (Nova Pro)."""
    import time as _time

    cache_file = BASE_DIR / "data" / "insights_cache.json"
    force = request.args.get("refresh", "").lower() == "true"

    if not force and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            age = _time.time() - cached.get("timestamp", 0)
            if age < 3600:
                return jsonify({"insights": cached.get("insights", [])})
        except Exception:
            pass

    items = load_items()

    compact = []
    for i in items:
        compact.append({
            "id": i.get("id", ""),
            "title": i.get("title", ""),
            "type": i.get("type", ""),
            "topic": i.get("topic", []),
            "region": i.get("region", []),
            "summary": (i.get("translation") or i.get("summary", ""))[:200],
            "source": i.get("source", ""),
        })

    system_prompt = (
        "You are analyzing a list of news, funding, and email items for an NGO. "
        "Identify genuine potential partnerships or collaboration opportunities - cases where "
        "two or more items suggest a meaningful connection (shared funders, overlapping geographic "
        "work, complementary campaigns, aligned timing). Only flag connections that are specific "
        "and plausible, not generic. Return a JSON object with an 'insights' array, each entry: "
        '{"label": "Potential partnership" or "Potential collaboration", '
        '"title_en": "short title in English", "title_de": "short title in German", '
        '"description_en": "one sentence in English explaining why", '
        '"description_de": "one sentence in German explaining why", '
        '"item_ids": ["id1", "id2"]}. '
        "Return at most 5 entries. If nothing genuinely stands out, return an empty array - "
        "do not invent weak connections."
    )

    try:
        content = chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(compact, ensure_ascii=False)[:12000]},
            ],
            tier="pro",
            temperature=0.3,
            max_tokens=2048,
            json_mode=True,
        )
        result = json.loads(content)
        insights_list = result.get("insights", [])
    except Exception as e:
        return jsonify({"insights": [], "error": f"AI analysis failed: {str(e)}"})

    # Cache the result
    try:
        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps({
            "timestamp": _time.time(),
            "insights": insights_list,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    return jsonify({"insights": insights_list})


@app.get("/api/markers")
def markers():
    """Return map markers with lat/lng for each location mentioned in items."""
    LOCATION_COORDS = {
        "burundi": [-3.37, 29.92], "bujumbura": [-3.36, 29.36], "gitega": [-3.43, 29.92],
        "kenya": [-0.02, 37.91], "rwanda": [-1.94, 29.87], "tanzania": [-6.37, 34.89],
        "uganda": [1.37, 32.29], "ethiopia": [9.15, 40.49], "drc": [-4.04, 21.76],
        "congo": [-4.04, 21.76], "south sudan": [6.88, 31.31], "somalia": [5.15, 46.20],
        "germany": [51.17, 10.45], "berlin": [52.52, 13.41], "bonn": [50.74, 7.10],
        "south africa": [-30.56, 22.94], "nigeria": [9.08, 8.68], "ghana": [7.95, -1.02],
        "malawi": [-13.25, 34.30], "zimbabwe": [-19.02, 29.15], "mozambique": [-18.67, 35.53],
        "mali": [17.57, -4.00], "senegal": [14.50, -14.45], "cameroon": [7.37, 12.35],
        "india": [20.59, 78.96], "thailand": [15.87, 100.99], "indonesia": [-0.79, 113.92],
        "global": [0.0, 20.0], "east africa": [-1.0, 34.0],
    }
    URGENCY_RANK = {"high": 3, "med": 2, "low": 1}

    items = load_items()
    loc_data = {}

    for item in items:
        for region in item.get("region", []):
            loc = region.strip().lower()
            if loc not in loc_data:
                loc_data[loc] = {"urgency": "low", "items": []}
            current_rank = URGENCY_RANK.get(loc_data[loc]["urgency"], 0)
            item_rank = URGENCY_RANK.get(item.get("priority", "low"), 0)
            if item_rank > current_rank:
                loc_data[loc]["urgency"] = item.get("priority", "low")
            loc_data[loc]["items"].append({
                "id": item.get("id", ""),
                "title": item.get("title", "")[:60],
                "type": item.get("type", ""),
                "urgency": item.get("priority", "low"),
            })

    result = []
    for loc, data in loc_data.items():
        coords = LOCATION_COORDS.get(loc)
        if not coords:
            for key, val in LOCATION_COORDS.items():
                if key in loc or loc in key:
                    coords = val
                    break
        if coords:
            result.append({
                "name": loc.title(),
                "lat": coords[0],
                "lng": coords[1],
                "urgency": data["urgency"],
                "count": len(data["items"]),
                "items": sorted(data["items"], key=lambda x: URGENCY_RANK.get(x["urgency"], 0), reverse=True)[:5],
            })

    return jsonify(result)


@app.post("/api/funding/search")
def funding_search():
    """Match a project description against funding opportunities using AWS Bedrock (Nova Pro)."""
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()

    if not query:
        return jsonify({"matches": [], "error": "No query provided."})

    items = load_items()
    funding_items = [i for i in items if i.get("type") == "funding"]

    if not funding_items:
        return jsonify({"matches": [], "error": "No funding opportunities available."})

    compact = []
    for f in funding_items:
        compact.append({
            "id": f.get("id", ""),
            "title": f.get("title", ""),
            "summary": f.get("translation") or f.get("summary", ""),
            "eligibility": f.get("eligibility", ""),
            "amount": f.get("amount", ""),
            "deadline": f.get("deadline", ""),
            "region": f.get("region", []),
            "topic": f.get("topic", []),
        })

    system_prompt = (
        "You are matching a project description against a list of funding opportunities. "
        "Given the project description and the list of opportunities (each with id, title, summary, "
        "eligibility, amount, deadline, region, topic), return a JSON object with a 'matches' array "
        "containing objects with 'id' (the opportunity id) and 'reason' (one sentence explaining why "
        "this is a good match). Only include genuinely relevant matches - return fewer results or even "
        "zero if nothing fits well. Order best-match-first."
    )

    user_msg = (
        f"Project description:\n{query}\n\n"
        f"Available funding opportunities:\n{json.dumps(compact, ensure_ascii=False)}"
    )

    try:
        content = chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg[:12000]},
            ],
            tier="pro",
            temperature=0.3,
            max_tokens=2048,
            json_mode=True,
        )
        result = json.loads(content)
        matched_ids = result.get("matches", [])
    except Exception as e:
        return jsonify({"matches": [], "error": f"AI matching failed: {str(e)}"})

    id_to_item = {i["id"]: i for i in funding_items}
    output = []
    for match in matched_ids:
        mid = match.get("id", "")
        reason = match.get("reason", "")
        if mid in id_to_item:
            item = dict(id_to_item[mid])
            item["matchReason"] = reason
            output.append(item)

    return jsonify({"matches": output})


@app.get("/api/meta")
def meta():
    return jsonify({
        "topics": [
            "Mobile Veterinary Support", "Stray Population Infrastructure",
            "Wildlife Trade Defenses", "Emergency Relief Hub",
            "Bildung", "Gesundheit",
            "Kinder- und Frauenrechte", "Kommunale Entwicklung und Umweltschutz",
        ],
        "regions": ["Burundi", "East Africa", "Germany", "India", "Thailand", "Malawi", "Indonesia", "Global"],
        "typeLabels": {
            "funding": "Funding", "news": "News", "email": "Email",
            "report": "Report", "alert": "Alert",
        },
    })


# ---------- Serve built frontend (optional) ----------------------------------

@app.get("/")
@app.get("/<path:path>")
def serve_spa(path: str = ""):
    if not CLIENT_DIR.exists():
        return (
            "Frontend build not found. Copy the React build output into "
            f"{CLIENT_DIR}, or run the React dev server separately.",
            200,
        )
    target = CLIENT_DIR / path
    if path and target.exists() and target.is_file():
        return send_from_directory(CLIENT_DIR, path)
    index = CLIENT_DIR / "index.html"
    if index.exists():
        return send_from_directory(CLIENT_DIR, "index.html")
    abort(404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
