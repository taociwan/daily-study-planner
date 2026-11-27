# -*- coding: utf-8 -*-
"""复盘模块：手写复盘 + AI 评价建议 + 基于近一周情况重排次日计划。"""
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session

from .auth import login_required
from .db import get_db, now_str
from .ai_client import chat_completion, AIConfigError

bp = Blueprint("review", __name__)

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _day_plans(db, user_id, plan_date):
    rows = db.execute(
        "SELECT start_time, end_time, description, status, elapsed_seconds "
        "FROM plans WHERE user_id=? AND plan_date=? ORDER BY start_time",
        (user_id, plan_date),
    ).fetchall()
    return [dict(r) for r in rows]


def _day_stats(plans):
    total = len(plans)
    done = sum(1 for p in plans if p["status"] == "completed")
    doing = sum(1 for p in plans if p["status"] == "in_progress")
    missed = sum(1 for p in plans if p["status"] == "not_completed")
    return {"total": total, "completed": done, "in_progress": doing, "not_completed": missed}


def _extract_json(text: str):
    """从模型回复中提取 JSON 对象；失败返回 None。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


@bp.route("/api/reviews", methods=["GET"])
@login_required
def get_review():
    user_id = session["user_id"]
    plan_date = request.args.get("date") or date.today().isoformat()
    db = get_db()
    row = db.execute(
        "SELECT * FROM reviews WHERE user_id=? AND review_date=?",
        (user_id, plan_date),
    ).fetchone()

    history = db.execute(
        "SELECT review_date, manual_text, ai_review, ai_advice, ai_suggestions "
        "FROM reviews WHERE user_id=? ORDER BY review_date DESC LIMIT 30",
        (user_id,),
    ).fetchall()
    history_list = []
    for h in history:
        item = dict(h)
        try:
            item["ai_suggestions"] = json.loads(item["ai_suggestions"] or "[]")
        except json.JSONDecodeError:
            item["ai_suggestions"] = []
        history_list.append(item)

    payload = {"review": None, "history": history_list}
    if row is not None:
        item = dict(row)
        try:
            item["ai_suggestions"] = json.loads(item["ai_suggestions"] or "[]")
        except json.JSONDecodeError:
            item["ai_suggestions"] = []
        payload["review"] = item
    return jsonify(payload)


@bp.route("/api/reviews", methods=["POST"])
@login_required
def save_review():
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    plan_date = data.get("date") or date.today().isoformat()
    manual_text = (data.get("manual_text") or "").strip()

    try:
        date.fromisoformat(plan_date)
    except ValueError:
        return jsonify({"error": "日期格式不正确"}), 400

    db = get_db()
    now = now_str()
    db.execute(
        """
        INSERT INTO reviews (user_id, review_date, manual_text, created_at, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(user_id, review_date) DO UPDATE SET
            manual_text=excluded.manual_text, updated_at=excluded.updated_at
        """,
        (user_id, plan_date, manual_text, now, now),
    )
    db.commit()
    return jsonify({"ok": True})


def _build_context(db, user_id, plan_date):
    today_plans = _day_plans(db, user_id, plan_date)
    today_stats = _day_stats(today_plans)

    history_stats = []
    today_d = date.fromisoformat(plan_date)
    for i in range(6, -1, -1):
        d = (today_d - timedelta(days=i)).isoformat()
        plans = _day_plans(db, user_id, d)
        stats = _day_stats(plans)
        history_stats.append({"date": d, "weekday": WEEKDAY_CN[date.fromisoformat(d).weekday()], **stats})

    return {
        "review_date": plan_date,
        "today": {"stats": today_stats, "plans": today_plans},
        "last_7_days": history_stats,
    }


@bp.route("/api/reviews/ai-review", methods=["POST"])
@login_required
def ai_review():
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    plan_date = data.get("date") or date.today().isoformat()
    try:
        date.fromisoformat(plan_date)
    except ValueError:
        return jsonify({"error": "日期格式不正确"}), 400

    db = get_db()
    cfg_row = db.execute("SELECT * FROM ai_config WHERE user_id=?", (user_id,)).fetchone()
    if cfg_row is None or not cfg_row["base_url"] or not cfg_row["model"]:
        return jsonify({"error": "请先在「设置」中配置 AI 模型后再使用 AI 复盘"}), 400

    context = _build_context(db, user_id, plan_date)
    context_json = json.dumps(context, ensure_ascii=False, indent=2)

    system = (
        "你是一名严格但鼓励人的学习规划教练。根据用户当天的计划完成情况和近一周统计，"
        "给出复盘评价、可执行的改进建议，并为第二天重新规划若干条具体、时段合理、可完成的学习任务。"
        "只输出 JSON，不要多余解释，字段如下：\n"
        '{\n'
        '  "review": "对当天表现的评价（2-4 句，点明完成率与亮点/不足）",\n'
        '  "advice": "改进建议（分点，具体可执行）",\n'
        '  "suggestions": [{"start_time": "HH:MM", "end_time": "HH:MM", "description": "任务内容"}]\n'
        "}\n"
        "suggestions 控制在 3-6 条，时间不冲突，结合近一周的薄弱项与习惯安排。"
    )
    user_prompt = f"以下是我的学习数据：\n{context_json}\n请按要求输出 JSON。"

    try:
        raw = chat_completion(
            {"base_url": cfg_row["base_url"], "api_key": cfg_row["api_key"],
             "model": cfg_row["model"]},
            [{"role": "system", "content": system},
             {"role": "user", "content": user_prompt}],
        )
    except AIConfigError as e:
        return jsonify({"error": str(e)}), 400

    parsed = _extract_json(raw)
    if parsed is None:
        review, advice, suggestions = raw, "", []
    else:
        review = str(parsed.get("review", "")).strip() or raw
        advice = str(parsed.get("advice", "")).strip()
        suggestions = parsed.get("suggestions") or []
        if not isinstance(suggestions, list):
            suggestions = []

    # 校验建议时段
    clean_suggestions = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        st = str(s.get("start_time", "")).strip()
        et = str(s.get("end_time", "")).strip()
        desc = str(s.get("description", "")).strip()
        if desc and len(st) == 5 and len(et) == 5 and et > st:
            clean_suggestions.append({"start_time": st, "end_time": et, "description": desc})

    now = now_str()
    db.execute(
        """
        INSERT INTO reviews (user_id, review_date, ai_review, ai_advice, ai_suggestions, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(user_id, review_date) DO UPDATE SET
            ai_review=excluded.ai_review,
            ai_advice=excluded.ai_advice,
            ai_suggestions=excluded.ai_suggestions,
            updated_at=excluded.updated_at
        """,
        (user_id, plan_date, review, advice, json.dumps(clean_suggestions, ensure_ascii=False), now, now),
    )
    db.commit()
    return jsonify({"ok": True, "review": review, "advice": advice,
                    "suggestions": clean_suggestions})


@bp.route("/api/reviews/apply-suggestions", methods=["POST"])
@login_required
def apply_suggestions():
    """把复盘里的次日建议写入第二天的计划（跳过冲突与重复）。"""
    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    plan_date = data.get("date") or date.today().isoformat()
    try:
        review_d = date.fromisoformat(plan_date)
    except ValueError:
        return jsonify({"error": "日期格式不正确"}), 400
    next_d = (review_d + timedelta(days=1)).isoformat()

    db = get_db()
    row = db.execute(
        "SELECT ai_suggestions FROM reviews WHERE user_id=? AND review_date=?",
        (user_id, plan_date),
    ).fetchone()
    if row is None:
        return jsonify({"error": "还没有可采纳的 AI 建议"}), 400
    try:
        suggestions = json.loads(row["ai_suggestions"] or "[]")
    except json.JSONDecodeError:
        suggestions = []

    existing = db.execute(
        "SELECT start_time, end_time, description FROM plans WHERE user_id=? AND plan_date=?",
        (user_id, next_d),
    ).fetchall()
    occupied = [
        (int(r["start_time"][:2]) * 60 + int(r["start_time"][3:]),
         int(r["end_time"][:2]) * 60 + int(r["end_time"][3:]))
        for r in existing
    ]
    titles = {(r["description"] or "").strip() for r in existing}

    inserted = 0
    skipped = 0
    for s in suggestions:
        st, et, desc = s.get("start_time"), s.get("end_time"), (s.get("description") or "").strip()
        if not desc or et <= st:
            skipped += 1
            continue
        sm = int(st[:2]) * 60 + int(st[3:])
        em = int(et[:2]) * 60 + int(et[3:])
        if desc in titles or any(sm < oe and em > os_ for os_, oe in occupied):
            skipped += 1
            continue
        try:
            db.execute(
                "INSERT INTO plans (user_id, plan_date, start_time, end_time, description, status, source) "
                "VALUES (?,?,?,?,?,'planned','ai')",
                (user_id, next_d, st, et, desc),
            )
            occupied.append((sm, em))
            titles.add(desc)
            inserted += 1
        except Exception:
            skipped += 1
    db.commit()
    return jsonify({"ok": True, "next_date": next_d, "inserted": inserted, "skipped": skipped})
