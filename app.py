# -*- coding: utf-8 -*-
"""每日学习计划 - Flask 入口

模块划分：
- modules.auth       注册 / 登录 / 登出 / 会话
- modules.plans      每日计划、长期目标、完成度统计
- modules.review     手写复盘 + AI 评价建议 + 次日计划重排
- modules.timetable  周课表
- modules.ai         AI 模型配置与聊天窗口
"""
import os

from flask import Flask

from modules.db import init_db, close_db
from modules import auth, plans, review, timetable, ai


def create_app():
    app = Flask(__name__)
    # 会话密钥优先取环境变量，未配置时运行时随机生成，不写入仓库
    app.secret_key = os.environ.get("STUDY_PLANNER_SECRET") or os.urandom(24)

    app.teardown_appcontext(close_db)

    app.register_blueprint(auth.bp)
    app.register_blueprint(plans.bp)
    app.register_blueprint(review.bp)
    app.register_blueprint(timetable.bp)
    app.register_blueprint(ai.bp)

    init_db()
    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=False)
