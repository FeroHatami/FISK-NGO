"""
Flask backend for the NGO Intelligence Hub.

Serves the prebuilt SPA from ./dist-spa and exposes JSON API endpoints
that mirror the frontend's mock data schema. Hook your Python pipeline
into the endpoints marked TODO.

Build the frontend first:
    npm install
    npm run build:spa

Then run:
    pip install -r requirements.txt
    python app.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

ROOT = Path(__file__).parent
DIST = ROOT / "dist-spa"
DATA = ROOT / "data"

app = Flask(__name__, static_folder=None)
CORS(app)


def _load(name: str):
    path = DATA / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- API ----------
@app.get("/api/items")
def list_items():
    # TODO: replace with your pipeline output
    items = _load("items.json")
    item_type = request.args.get("type")
    if item_type:
        items = [i for i in items if i.get("type") == item_type]
    return jsonify(items)


@app.get("/api/items/<item_id>")
def get_item(item_id: str):
    items = _load("items.json")
    for i in items:
        if i.get("id") == item_id:
            return jsonify(i)
    return jsonify({"error": "not_found"}), 404


@app.get("/api/briefing")
def briefing():
    # TODO: return today's AI-generated briefing
    return jsonify({
        "date": "2026-06-28",
        "summary": "3 funding calls, 2 partner updates, 1 urgent action.",
        "highlights": [],
    })


@app.post("/api/copilot")
def copilot():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question", "")
    # TODO: route to your LLM / RAG pipeline
    return jsonify({"answer": f"(stub) You asked: {question}"})


# ---------- Static SPA ----------
@app.get("/")
def index():
    return send_from_directory(DIST, "index.html")


@app.get("/<path:path>")
def static_or_spa(path: str):
    target = DIST / path
    if target.is_file():
        return send_from_directory(DIST, path)
    # SPA fallback: client-side router handles the route
    return send_from_directory(DIST, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
