# 每日学习计划 · Daily Study Planner

一个轻量的本地学习计划管理工具：把一天的 24 小时切成时间段安排学习任务，到点提醒、记录完成情况，并支持手写复盘、AI 复盘规划、周课表和外接 AI 助手。

后端是 Flask 应用，数据存 SQLite，前端是原生 HTML/CSS/JS，不依赖任何构建工具。双击启动就能用，适合学生和自学者做每日时间管理。

## 功能特性

### 账号与登录
- 用户名 + 密码注册 / 登录，密码用 PBKDF2-HMAC-SHA256 加盐哈希存储（纯标准库，无第三方加密依赖）
- Flask Session 维持登录态，接口按会话识别用户，不再由前端传用户 ID
- 支持退出登录；未登录访问接口返回 401 并跳回登录页

### 24 小时计划表（主页）
- 登录后主页面即当日计划与完成度：总计划 / 已完成 / 进行中 / 未完成 / 完成率
- 时间轴可视化 + 列表两种视图，支持添加、编辑、删除计划
- 每条计划可「开始」倒计时；达到时长 80% 认定完成，到 100% 记录最终用时
- 到点未开始自动标记「未完成」；过期任务可「结束任务」或「延顺任务」

### 庆祝弹窗
- 单条计划完成：弹出「恭喜完成该计划」彩带弹窗
- 当天全部完成：弹出「恭喜完成今天的全部任务」收官弹窗
- 弹窗带彩带飘落动画与提示音，每次会话内不重复打扰

### 复盘总结
- 手写复盘：按日期记录当天完成情况、收获、不足、心情
- AI 复盘：读取当天计划与近 7 天完成统计，给出评价、改进建议和次日任务建议
- 采纳建议：一键把 AI 给出的次日计划加入第二天日程（时间冲突 / 重复自动跳过）
- 历史复盘列表可回溯

### 周课表
- 按周一~周日维护每周固定课程：星期、上课/下课时间、课程名、地点
- 七列周视图展示，支持添加、编辑、删除

### AI 智能助手
- 侧边栏聊天窗口，多轮对话，本地保存最近对话记录，可清空
- 支持任意 OpenAI 兼容接口：DeepSeek、通义、智谱、Ollama 本地模型等
- 在「设置」中配置 Base URL、模型名、API Key、系统提示词，可测试连接
- 密钥仅保存在本机数据库，接口不回显完整密钥

### 自动生成计划 / 长期目标
- 打开某天自动补全计划：长期目标 → 过去 28 天同星期几高频任务和历史时段
- 长期目标含名称、每日任务、日期范围、每日时段、执行星期；冲突自动跳过
- 历史习惯每个日期只生成一次，手动改过的计划不会被自动恢复，可点「重新生成」

## 技术栈

| 层 | 选型 |
| --- | --- |
| 后端 | Python 3 + Flask 3，按功能拆分 Blueprints 模块 |
| 数据库 | SQLite（内置 sqlite3，无需额外服务） |
| 前端 | 原生 HTML + CSS + JavaScript（无框架、无打包） |
| AI 调用 | 标准库 urllib，OpenAI 兼容 `/chat/completions` |
| 运行方式 | 本地 Flask 服务，默认 `http://127.0.0.1:5001` |

依赖极简，`requirements.txt` 只需要 `flask>=2.0`。

## 目录结构

```
每日学习计划/
├── app.py                  # Flask 入口：创建应用、注册蓝图、初始化数据库
├── requirements.txt        # Python 依赖
├── modules/                # 后端按功能拆分的模块
│   ├── db.py               # 数据库连接、建表、密码哈希
│   ├── auth.py             # 注册 / 登录 / 登出 / 会话校验
│   ├── plans.py            # 每日计划、长期目标、完成度统计
│   ├── review.py           # 手写复盘、AI 评价建议、次日规划采纳
│   ├── timetable.py        # 周课表增删改查
│   ├── ai.py               # AI 配置、聊天记录、连接测试
│   └── ai_client.py        # OpenAI 兼容接口调用封装
├── templates/
│   ├── auth.html           # 登录 / 注册页
│   └── app.html            # 主应用框架（侧边栏 + 五个标签页）
├── static/
│   ├── css/style.css       # 全部样式
│   └── js/
│       ├── common.js       # 会话、导航、Toast、庆祝弹窗、请求封装
│       ├── plans.js        # 今日计划、计时、提醒、长期目标
│       ├── review.js        # 复盘与 AI 规划
│       ├── timetable.js    # 周课表
│       ├── ai_chat.js      # AI 聊天窗口
│       ├── settings.js     # AI 配置与账号信息
│       └── auth.js         # 登录 / 注册表单
├── 启动学习计划.command      # macOS 双击启动
├── 停止学习计划.command      # macOS 双击停止
├── LICENSE
└── README.md
```

> `study_planner.db`、`server.log`、`venv/` 都在 `.gitignore` 里，运行后本地生成，不进入仓库。

## 快速开始

要求：Python 3.9 及以上。

```bash
git clone https://github.com/taociwan/daily-study-planner.git
cd daily-study-planner

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

浏览器打开 `http://127.0.0.1:5001`（5001 避开 macOS AirPlay 占用的 5000 端口）。

### macOS 一键启动

双击 `启动学习计划.command`：自动用 venv 里的 Python 后台起服务并打开浏览器；已在运行则直接打开页面。双击 `停止学习计划.command` 结束进程。

## 配置 AI 模型

进入「设置 → AI 模型配置」：

- **接口地址 Base URL**：如 `https://api.deepseek.com/v1`、`https://open.bigmodel.cn/api/paas/v4`，或本地 Ollama 的 `http://127.0.0.1:11434/v1`
- **模型名称**：如 `deepseek-chat`、`glm-4-flash`、`qwen-plus`
- **API Key**：留空表示不修改已保存的密钥
- **系统提示词**：可选，定义助手角色与回答风格
- 点「测试连接」验证接口是否可用

未配置 AI 时，复盘和聊天会提示先填写接口信息，不影响计划、课表等本地功能。

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/register` | 注册账号 |
| POST | `/api/login` | 登录，写入会话 |
| POST | `/api/logout` | 退出登录 |
| GET | `/api/me` | 当前登录用户 |
| GET/POST | `/api/plans` | 查询 / 新增某天计划 |
| PUT/DELETE | `/api/plans/<id>` | 编辑 / 删除计划 |
| POST | `/api/plans/generate` | 重新生成当天自动计划 |
| POST | `/api/plans/<id>/start` | 开始计划 |
| POST | `/api/plans/<id>/complete` | 标记完成 |
| POST | `/api/plans/<id>/close` | 结束未完成任务 |
| POST | `/api/plans/<id>/postpone` | 延顺任务 |
| GET/POST | `/api/goals` | 查询 / 新建长期目标 |
| PUT/DELETE | `/api/goals/<id>` | 修改 / 删除长期目标 |
| GET | `/api/summary` | 当天完成度统计 |
| GET/POST | `/api/reviews` | 查询 / 保存手写复盘 |
| POST | `/api/reviews/ai-review` | AI 复盘评价与次日建议 |
| POST | `/api/reviews/apply-suggestions` | 采纳建议到第二天计划 |
| GET/POST | `/api/timetable` | 查询 / 新增课程 |
| PUT/DELETE | `/api/timetable/<id>` | 修改 / 删除课程 |
| GET/PUT | `/api/ai/config` | 读取 / 保存 AI 配置 |
| POST | `/api/ai/chat` | 发送聊天消息 |
| GET | `/api/ai/history` | 聊天历史 |
| POST | `/api/ai/clear` | 清空对话 |
| POST | `/api/ai/test` | 测试 AI 连接 |

## 数据与隐私

- 所有计划、复盘、课表、对话记录存本地 `study_planner.db`
- AI Key 仅存本机数据库，接口返回时不回显；仓库不包含任何个人数据
- 首次运行自动建表；旧版无密码的历史账号需要重新注册后使用

## 许可证

本项目基于 [MIT License](LICENSE) 开源，可自由使用、修改、分发，保留版权声明即可。
