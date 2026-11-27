# -*- coding: utf-8 -*-
"""AI 配置与聊天模块：外接任意 OpenAI 兼容模型。"""
import json
from datetime import date, timedelta

from flask import Blueprint, jsonify, request, session

from .auth import login_required
from .db import get_db, now_str
from .ai_client import chat_completion, AIConfigError

bp = Blueprint("ai", __name__)


def _load_config(user_id: int):
    row = get_db().execute(
        "SELECT * FROM ai_config WHERE user_id=?", (user_id,)
    ).fetchone()
    if row is None:
        return {"base_url": "", "api_key": "", "model": "", "system_prompt": ""}
    return {
        "base_url": row["base_url"],
        "api_key": row["api_key"],
        "model": row["model"],
        "system_prompt": row["system_prompt"],
    }


@bp.route("/api/ai/config", methods=["GET"])
@login_required
def get_config():
    user_id = session["user_id"]
    cfg = _load_config(user_id)
    return jsonify({
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "system_prompt": cfg["system_prompt"],
        "has_key": bool(cfg["api_key"]),
    })


@bp.route("/api/ai/config", methods=["PUT"])
@login_required
def save_config():
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    base_url = (data.get("base_url") or "").strip()
    model = (data.get("model") or "").strip()
    system_prompt = (data.get("system_prompt") or "").strip()
    # api_key 传空串表示不修改；传 "*" 之外的非空值则更新
    api_key = data.get("api_key")
    keep_key = api_key in (None, "")

    db = get_db()
    existing = db.execute("SELECT * FROM ai_config WHERE user_id=?", (user_id,)).fetchone()
    if existing is None:
        db.execute(
            "INSERT INTO ai_config (user_id, base_url, api_key, model, system_prompt, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, base_url, "" if keep_key else api_key, model, system_prompt, now_str()),
        )
    else:
        new_key = existing["api_key"] if keep_key else api_key
        db.execute(
            "UPDATE ai_config SET base_url=?, api_key=?, model=?, system_prompt=?, updated_at=? "
            "WHERE user_id=?",
            (base_url, new_key, model, system_prompt, now_str(), user_id),
        )
    db.commit()
    return jsonify({"ok": True, "has_key": bool(keep_key and existing["api_key"] or api_key)})


@bp.route("/api/ai/chat", methods=["POST"])
@login_required
def chat():
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "请输入内容"}), 400

    cfg = _load_config(user_id)
    db = get_db()

    history = db.execute(
        "SELECT role, content FROM chat_messages WHERE user_id=? "
        "ORDER BY id DESC LIMIT 10",
        (user_id,),
    ).fetchall()
    history = list(reversed(history))

    system = cfg["system_prompt"] or (
        "你是用户的学习助手，回答简洁、有条理，鼓励用户坚持计划。"
    )
    messages = [{"role": "system", "content": system}]
    messages += [{"role": r["role"], "content": r["content"]} for r in history]
    messages.append({"role": "user", "content": message})

    try:
        reply = chat_completion(cfg, messages)
    except AIConfigError as e:
        return jsonify({"error": str(e)}), 400

    now = now_str()
    db.execute(
        "INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?,?,?,?)",
        (user_id, "user", message, now),
    )
    db.execute(
        "INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?,?,?,?)",
        (user_id, "assistant", reply, now),
    )
    db.commit()
    return jsonify({"ok": True, "reply": reply})


@bp.route("/api/ai/history", methods=["GET"])
@login_required
def chat_history():
    user_id = session["user_id"]
    rows = get_db().execute(
        "SELECT role, content, created_at FROM chat_messages WHERE user_id=? "
        "ORDER BY id DESC LIMIT 30",
        (user_id,),
    ).fetchall()
    return jsonify([dict(r) for r in reversed(rows)])


@bp.route("/api/ai/clear", methods=["POST"])
@login_required
def clear_history():
    db = get_db()
    db.execute("DELETE FROM chat_messages WHERE user_id=?", (session["user_id"],))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/ai/test", methods=["POST"])
@login_required
def test_connection():
    cfg = _load_config(session["user_id"])
    try:
        reply = chat_completion(
            cfg,
            [{"role": "user", "content": "你好，请用一句话确认连接成功。"}],
            timeout=20,
        )
    except AIConfigError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "reply": reply})
