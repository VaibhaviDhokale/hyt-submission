"""Tally web app: JSON API (Flask) + a static Tailwind/vanilla-JS triage inbox.

    .venv/bin/python -m web.app          # http://localhost:5057
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tally import golden, llm, screen, store  # noqa: E402
from tally.clean import clean_resume  # noqa: E402
from tally.config import path, read_json  # noqa: E402

STATIC = Path(__file__).parent / "static"
app = Flask(__name__, static_folder=None)
UPLOADS: dict[str, dict[str, dict]] = {}  # job -> cand -> resume record (memory only, never written to disk)


def _job(job_id: str) -> dict:
    j = screen.jobs().get(job_id)
    if not j:
        abort(404)
    return j


def _summary(r: dict) -> dict:
    musts = [c for c in r["checklist"] if c["kind"] == "must"]
    return {"cand": r["cand"], "score": r["score"], "lane": r["lane"], "reasons": r["reasons"],
            "headline": r["profile"]["headline"], "years": r["years"]["relevant"],
            "musts_met": sum(c["verdict"] == "met" for c in musts), "musts": len(musts)}


def _ranked(job_id: str) -> tuple[list[dict], int]:
    res, pending = screen.rank(job_id, golden.pairs_for(job_id))
    for cid, rec in UPLOADS.get(job_id, {}).items():
        try:
            res.append({"cand": cid, "uploaded": True, **screen.screen_text(job_id, rec["text"], rec)})
        except llm.Pending:
            pending += 1
    res.sort(key=lambda r: -r["score"])
    return res, pending


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(STATIC, name)


@app.get("/api/jobs")
def list_jobs():
    out = []
    for jid, j in screen.jobs().items():
        res, pending = _ranked(jid)
        acts = store.actions(jid)
        out.append({"id": jid, "title": j["title"], "company": j["company"], "location": j["location"],
                    "level": j["level"], "split": j["split"], "pending": pending,
                    "lanes": {ln: sum(r["lane"] == ln for r in res) for ln in screen.LANES},
                    "decided": sum(1 for r in res if r["cand"] in acts), "total": len(res)})
    return jsonify({"jobs": out, "llm": llm.status()})


@app.get("/api/jobs/<job_id>")
def job_detail(job_id):
    j = _job(job_id)
    try:
        chk = screen.job_checklist(job_id)
    except llm.Pending:
        chk = None
    res, pending = _ranked(job_id)
    acts = store.actions(job_id)
    cands = [{**_summary(r), "action": acts.get(r["cand"], {}).get("action"), "uploaded": r.get("uploaded", False)}
             for r in res]
    return jsonify({"job": {k: j[k] for k in ("id", "title", "company", "location", "level", "work_type", "text")},
                    "checklist": chk, "candidates": cands, "pending": pending, "thresholds": screen.thresholds(),
                    "reason_help": screen.REASONS})


@app.get("/api/jobs/<job_id>/candidates/<cand>")
def cand_detail(job_id, cand):
    _job(job_id)
    rec = UPLOADS.get(job_id, {}).get(cand) or screen.resumes().get(cand)
    if not rec:
        abort(404)
    try:
        r = screen.screen_text(job_id, rec["text"], rec)
    except llm.Pending:
        return jsonify({"pending": True}), 202
    a = store.actions(job_id).get(cand)
    return jsonify({**r, "cand": cand, "resume": rec["text"], "action": a})


@app.post("/api/jobs/<job_id>/candidates/<cand>/action")
def act(job_id, cand):
    _job(job_id)
    body = request.get_json(force=True)
    action, note = body.get("action"), (body.get("note") or "").strip()
    if action not in ("advance", "hold", "pass", "undo"):
        return jsonify({"error": "unknown action"}), 400
    if action == "pass" and len(note) < 5:
        return jsonify({"error": "Passing on a candidate needs a short written reason."}), 400
    store.log_action(job_id, cand, action, note)
    return jsonify({"ok": True})


@app.post("/api/jobs/<job_id>/upload")
def upload(job_id):
    """Paste or upload a plain-text resume. Kept in memory for this server session only."""
    _job(job_id)
    f = request.files.get("file")
    raw = f.read().decode("utf-8", "replace") if f else (request.form.get("text") or "")
    if len(raw.split()) < 30:
        return jsonify({"error": "Resume text is too short (need at least 30 words)."}), 400
    rec = clean_resume(raw.replace("\n", "   "))
    cid = f"U{len(UPLOADS.setdefault(job_id, {})) + 1:02d}"
    UPLOADS[job_id][cid] = {"id": cid, **rec}
    try:
        screen.screen_text(job_id, rec["text"], rec)
        return jsonify({"cand": cid, "pending": False})
    except llm.Pending:
        return jsonify({"cand": cid, "pending": True,
                        "message": "Queued for the LLM (provider=queue). Answer the queue, then refresh."})


@app.get("/api/metrics")
def metrics():
    out = {}
    for name in ("metrics", "baselines", "fairness", "judge", "extraction", "thresholds", "adversarial"):
        f = path("results") / f"{name}.json"
        out[name] = read_json(f) if f.exists() else None
    return jsonify(out)


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5057)), debug=False)
