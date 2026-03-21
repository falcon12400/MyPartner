from http.server import BaseHTTPRequestHandler
from openai import OpenAI
from urllib import request as urllib_request
from urllib import error as urllib_error
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any

# -----------------------------
# Environment
# -----------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
APP_MODE = os.environ.get("APP_MODE", "direct_gpt").strip().lower()

ENABLE_INSPECT_INSERT = os.environ.get("ENABLE_INSPECT_INSERT", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
ENABLE_ACK_REPLY = os.environ.get("ENABLE_ACK_REPLY", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
SAVE_ASSISTANT_REPLY = os.environ.get("SAVE_ASSISTANT_REPLY", "true").strip().lower() in {
    "1", "true", "yes", "on"
}

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
DEFAULT_AGENT_ID = os.environ.get("DEFAULT_AGENT_ID", "a_main")
ACK_REPLY_TEXT = os.environ.get("ACK_REPLY_TEXT", "收到，我正在處理。")

STATE_PENDING = 0

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# -----------------------------
# Utilities
# -----------------------------
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def debug_log(message: str, payload: dict[str, Any] | None = None) -> None:
    if payload is None:
        print(message)
        return
    try:
        print(f"{message}: {json.dumps(payload, ensure_ascii=False)}")
    except Exception:
        print(message)


def generate_short_id(prefix: str) -> str:
    """Generate IDs like m_XXXXXXXX or u_XXXXXXXX."""
    return f"{prefix}_{secrets.token_hex(4).upper()}"


def normalize_user_id(line_user_id: str | None) -> str:
    """
    Convert LINE userId into a stable short ID.
    Keeps only 8 hex chars for readability and stability.
    """
    if not line_user_id:
        return generate_short_id("u")
    digest = hashlib.sha256(line_user_id.encode("utf-8")).hexdigest()[:8].upper()
    return f"u_{digest}"


def require_env(name: str, value: str) -> None:
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")


def json_response(handler: BaseHTTPRequestHandler, status_code: int, body: dict[str, Any]) -> None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


# -----------------------------
# LINE parsing
# -----------------------------
def parse_line_message(event: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert a LINE event into internal Message schema.

    Message schema:
    {
      "message_id": "m_XXXXXXXX",
      "from": "u_XXXXXXXX",
      "to": "a_main",
      "line_user_id": "Uxxxxxxxx",
      "content": [...],
      "created_at": "ISO8601"
    }
    """
    if event.get("type") != "message":
        return None

    source = event.get("source", {})
    line_user_id = source.get("userId")
    from_id = normalize_user_id(line_user_id)

    msg = event.get("message", {})
    msg_type = msg.get("type")
    content: list[dict[str, Any]] = []

    if msg_type == "text":
        content.append({
            "type": "text",
            "text": msg.get("text", "")
        })
    elif msg_type == "image":
        content.append({
            "type": "image",
            "file_id": msg.get("id", ""),
            "source": "line"
        })
    elif msg_type == "audio":
        content.append({
            "type": "audio",
            "file_id": msg.get("id", ""),
            "duration_ms": msg.get("duration", 0),
            "source": "line"
        })
    elif msg_type == "video":
        content.append({
            "type": "video",
            "file_id": msg.get("id", ""),
            "duration_ms": msg.get("duration", 0),
            "source": "line"
        })
    elif msg_type == "file":
        content.append({
            "type": "file",
            "file_id": msg.get("id", ""),
            "file_name": msg.get("fileName", ""),
            "file_size": msg.get("fileSize", 0),
            "source": "line"
        })
    else:
        content.append({
            "type": "unknown",
            "raw_type": msg_type or "unknown"
        })

    return {
        "message_id": generate_short_id("m"),
        "from": from_id,
        "to": DEFAULT_AGENT_ID,
        "line_user_id": line_user_id,
        "content": content,
        "created_at": utc_now_iso()
    }


def build_inspect_reply(message_obj: dict[str, Any]) -> str:
    content_types = [item.get("type", "unknown") for item in message_obj.get("content", [])]
    preview = get_first_text(message_obj)[:50] if has_text(message_obj) else ""

    return (
        f"mode=inspect\n"
        f"from={message_obj['from']}\n"
        f"to={message_obj['to']}\n"
        f"message_id={message_obj['message_id']}\n"
        f"content_types={', '.join(content_types)}\n"
        f"preview={preview}"
    )


def get_first_text(message_obj: dict[str, Any]) -> str:
    for item in message_obj.get("content", []):
        if item.get("type") == "text":
            return str(item.get("text", ""))
    return ""


def has_text(message_obj: dict[str, Any]) -> bool:
    return any(item.get("type") == "text" for item in message_obj.get("content", []))


def build_assistant_message(user_message_obj: dict[str, Any], answer: str) -> dict[str, Any]:
    return {
        "message_id": generate_short_id("m"),
        "from": DEFAULT_AGENT_ID,
        "to": user_message_obj["from"],
        "line_user_id": None,
        "content": [
            {
                "type": "text",
                "text": answer
            }
        ],
        "created_at": utc_now_iso()
    }


# -----------------------------
# Supabase
# -----------------------------
def insert_message_to_supabase(message_obj: dict[str, Any], state_code: int = STATE_PENDING) -> bool:
    """
    Insert into public.messages:
    - message_id
    - from_id
    - to_id
    - line_user_id
    - content
    - state_code
    - created_at
    """
    require_env("SUPABASE_URL", SUPABASE_URL)
    require_env("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY)

    url = f"{SUPABASE_URL}/rest/v1/messages"
    payload = {
        "message_id": message_obj["message_id"],
        "from_id": message_obj["from"],
        "to_id": message_obj["to"],
        "line_user_id": message_obj.get("line_user_id"),
        "content": message_obj["content"],
        "state_code": state_code,
        "created_at": message_obj["created_at"],
    }

    req = urllib_request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            debug_log("Supabase insert success", {"status": resp.status, "message_id": message_obj["message_id"]})
            return True
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        debug_log("Supabase insert failed", {"status": exc.code, "body": error_body, "message_id": message_obj["message_id"]})
        return False
    except Exception as exc:
        debug_log("Supabase insert exception", {"error": str(exc), "message_id": message_obj["message_id"]})
        return False


# -----------------------------
# LINE reply / push
# -----------------------------
def reply_line(reply_token: str, text: str) -> bool:
    require_env("LINE_CHANNEL_ACCESS_TOKEN", LINE_CHANNEL_ACCESS_TOKEN)

    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": text[:4500],
            }
        ],
    }

    req = urllib_request.Request(
        url="https://api.line.me/v2/bot/message/reply",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            debug_log("LINE reply success", {"status": resp.status})
            return True
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        debug_log("LINE reply failed", {"status": exc.code, "body": error_body})
        return False
    except Exception as exc:
        debug_log("LINE reply exception", {"error": str(exc)})
        return False


def push_to_line(line_user_id: str, text: str) -> bool:
    require_env("LINE_CHANNEL_ACCESS_TOKEN", LINE_CHANNEL_ACCESS_TOKEN)

    payload = {
        "to": line_user_id,
        "messages": [
            {
                "type": "text",
                "text": text[:4500],
            }
        ],
    }

    req = urllib_request.Request(
        url="https://api.line.me/v2/bot/message/push",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=10) as resp:
            debug_log("LINE push success", {"status": resp.status})
            return True
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        debug_log("LINE push failed", {"status": exc.code, "body": error_body})
        return False
    except Exception as exc:
        debug_log("LINE push exception", {"error": str(exc)})
        return False


# -----------------------------
# Mode handlers
# -----------------------------
def handle_echo(reply_token: str, message_obj: dict[str, Any]) -> None:
    if has_text(message_obj):
        text = get_first_text(message_obj)
    else:
        text = "已收到非文字訊息"
    reply_line(reply_token, text)


def handle_inspect(reply_token: str, message_obj: dict[str, Any]) -> None:
    if ENABLE_INSPECT_INSERT:
        insert_message_to_supabase(message_obj, state_code=STATE_PENDING)
    reply_line(reply_token, build_inspect_reply(message_obj))


def handle_direct_gpt(reply_token: str, message_obj: dict[str, Any]) -> None:
    # Save user message first, but do not crash if DB insert fails.
    insert_message_to_supabase(message_obj, state_code=STATE_PENDING)

    if not has_text(message_obj):
        reply_line(reply_token, "已收到非文字訊息，目前 direct_gpt 模式先不處理這類內容。")
        return

    require_env("OPENAI_API_KEY", OPENAI_API_KEY)
    if client is None:
        raise RuntimeError("OpenAI client is not initialized.")

    user_text = get_first_text(message_obj)

    try:
        resp = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "你是透過 LINE 提供服務、由 OpenAI 模型驅動的 AI 助手，"
                        "請用繁體中文簡潔回覆。"
                    ),
                },
                {
                    "role": "user",
                    "content": user_text,
                },
            ],
        )
        answer = (resp.output_text or "").strip()
        if not answer:
            answer = "我目前沒有產生有效回覆。"

        reply_ok = reply_line(reply_token, answer)

        if SAVE_ASSISTANT_REPLY and reply_ok:
            assistant_message = build_assistant_message(message_obj, answer)
            insert_message_to_supabase(assistant_message, state_code=STATE_PENDING)

    except Exception as exc:
        debug_log("OpenAI exception", {"error": str(exc)})
        reply_line(reply_token, "抱歉，我剛剛處理失敗了，請稍後再試一次。")


def handle_ack_store(reply_token: str, message_obj: dict[str, Any]) -> None:
    # 先簡短回覆，再寫入資料庫，後續交由本機 worker 處理
    if ENABLE_ACK_REPLY:
        reply_line(reply_token, ACK_REPLY_TEXT)
    insert_message_to_supabase(message_obj, state_code=STATE_PENDING)


# -----------------------------
# Request handler
# -----------------------------
class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        json_response(self, 200, {
            "ok": True,
            "message": "webhook running",
            "mode": APP_MODE,
            "default_agent_id": DEFAULT_AGENT_ID,
            "inspect_insert_enabled": ENABLE_INSPECT_INSERT,
            "ack_reply_enabled": ENABLE_ACK_REPLY,
            "save_assistant_reply": SAVE_ASSISTANT_REPLY,
            "ack_reply_text": ACK_REPLY_TEXT,
            "state_pending_code": STATE_PENDING,
            "openai_configured": bool(OPENAI_API_KEY),
            "line_configured": bool(LINE_CHANNEL_ACCESS_TOKEN),
            "supabase_configured": bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        })

    def do_POST(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            json_response(self, 400, {"ok": False, "error": "invalid_json"})
            return

        events = body.get("events", [])
        if not isinstance(events, list):
            json_response(self, 400, {"ok": False, "error": "invalid_events"})
            return

        handled = 0

        for event in events:
            reply_token = event.get("replyToken")
            if not reply_token:
                debug_log("Skip event without replyToken", {"event": event})
                continue

            message_obj = parse_line_message(event)
            if message_obj is None:
                debug_log("Skip non-message event", {"event_type": event.get("type")})
                continue

            try:
                if APP_MODE == "echo":
                    handle_echo(reply_token, message_obj)
                elif APP_MODE == "inspect":
                    handle_inspect(reply_token, message_obj)
                elif APP_MODE == "direct_gpt":
                    handle_direct_gpt(reply_token, message_obj)
                elif APP_MODE == "ack_store":
                    handle_ack_store(reply_token, message_obj)
                else:
                    reply_line(reply_token, f"未知模式：{APP_MODE}")
                handled += 1
            except RuntimeError as exc:
                debug_log("Configuration/runtime error", {"error": str(exc)})
                reply_line(reply_token, f"系統設定錯誤：{str(exc)}")
            except Exception as exc:
                debug_log("Unhandled event error", {"error": str(exc)})
                reply_line(reply_token, "系統發生未預期錯誤，請稍後再試。")

        json_response(self, 200, {"ok": True, "handled": handled})
