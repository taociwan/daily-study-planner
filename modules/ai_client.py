# -*- coding: utf-8 -*-
"""OpenAI 兼容接口调用（纯标准库 urllib，无需额外依赖）。"""
import json
import urllib.request
import urllib.error


class AIConfigError(Exception):
    pass


def _normalize_base_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise AIConfigError("尚未配置 AI 接口地址，请先在「设置」中填写")
    # 兼容填写到 /v1 或 /chat/completions 的情况
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return base


def chat_completion(config: dict, messages: list, timeout: int = 60) -> str:
    """调用 OpenAI 兼容的 /chat/completions，返回文本回复。

    config: {base_url, api_key, model, system_prompt?}
    messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    base = _normalize_base_url(config.get("base_url", ""))
    model = (config.get("model") or "").strip()
    if not model:
        raise AIConfigError("尚未配置模型名称，请先在「设置」中填写")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "stream": False,
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if config.get("api_key"):
        headers["Authorization"] = f"Bearer {config['api_key']}"

    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:300]
        raise AIConfigError(f"接口返回错误 {e.code}：{body}")
    except urllib.error.URLError as e:
        raise AIConfigError(f"无法连接 AI 接口：{e.reason}")
    except TimeoutError:
        raise AIConfigError("AI 接口响应超时，请稍后重试")

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise AIConfigError("AI 返回格式异常，请检查模型配置")
