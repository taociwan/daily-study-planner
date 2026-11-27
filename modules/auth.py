# -*- coding: utf-8 -*-
"""认证模块：注册 / 登录 / 登出 / 当前用户（Flask Session）。"""
import re
import sqlite3
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, session

from .db import get_db, now_str, hash_password, verify_password

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    row = get_db().execute(
        "SELECT id, username, name, age, gender FROM users WHERE id=?",
        (uid,),
    ).fetchone()
    return row


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "未登录，请先登录"}), 401
        return view(*args, **kwargs)
    return wrapper


@bp.route("/")
def auth_page():
    if session.get("user_id"):
        return render_template("app.html")
    return render_template("auth.html")


@bp.route("/app")
def app_page():
    return render_template("app.html")


@bp.route("/api/me")
def me():
    user = current_user()
    if user is None:
        return jsonify({"error": "未登录"}), 401
    return jsonify(dict(user))


@bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    age = data.get("age")
    gender = data.get("gender")

    if not USERNAME_RE.match(username):
        return jsonify({"error": "用户名需为 3-20 位字母、数字或下划线"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少 6 位"}), 400
    if not name:
        return jsonify({"error": "请填写昵称"}), 400
    if gender not in ("male", "female"):
        return jsonify({"error": "请选择性别"}), 400
    try:
        age = int(age)
        if not 1 <= age <= 120:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "请填写正确的年龄"}), 400

    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "该用户名已被注册，换一个试试"}), 409

    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, name, age, gender, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (username, hash_password(password), name, age, gender, now_str()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            return jsonify({"error": "该用户名已被注册，换一个试试"}), 409
        return jsonify({"error": "昵称已被占用，换个昵称重试"}), 409
    session["user_id"] = cur.lastrowid
    return jsonify({"id": cur.lastrowid, "username": username, "name": name,
                    "age": age, "gender": gender})


@bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "请输入用户名和密码"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if row is None or not row["password_hash"] or not verify_password(password, row["password_hash"]):
        return jsonify({"error": "用户名或密码不正确"}), 401

    session["user_id"] = row["id"]
    return jsonify({"id": row["id"], "username": row["username"], "name": row["name"],
                    "age": row["age"], "gender": row["gender"]})


@bp.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})
