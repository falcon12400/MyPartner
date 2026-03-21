from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler
import json
import os
import uuid

import requests
from openai import OpenAI


APP_MODE = os.environ.get("APP_MODE", "direct_gpt").strip().lower()
INSPECT_WRITE_SUPABASE = (
    os.environ.get("INSPECT_WRITE_SUPABASE", "false").strip().lower() == "true"
)
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

OPENAI_MODEL = "gpt-4.1-mini"
AGENT_ID = "a_main"
SYSTEM_PROMPT = (
    "你是透過 LINE 提供服務、由 OpenAI 模型驅動的 AI 助手，"
    "請用繁體中文簡潔回覆。"
)

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def generate_short_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def normalize_user_id(line_user_id):
    if not line_user_id:
        return "system"

    digest = sha256(line_user_id.encode("utf-8")).hexdigest()[:8]
    return f"u_{digest}"


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def parse_json_request(handler):
    content_length = int(handler.headers.get("Content-Length", 0))
    raw_body = handler.rfile.read(content_length)

    if not raw_body:
        return {}

    return json.loads(raw_body.decode("utf-8"))


def send_json(handler, status_code, payload):
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def error_response(handler, status_code, message):
    send_json(handler, status_code, {"ok": False, "error": message})


def require_env_vars(names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        return f"Missing required environment variables: {', '.join(missing)}"
    return None


def parse_content_item(line_message):
    message_type = line_message.get("type")
    if message_type == "text":
        return {"type": "text", "text": line_message.get("text", "")}
    if message_type == "image":
        return {"type": "image", "file_id": line_message.get("id")}
    if message_type == "audio":
        return {
            "type": "audio",
            "file_id": line_message.get("id"),
            "duration_ms": line_message.get("duration"),
        }
    if message_type == "video":
        return {"type": "video", "file_id": line_message.get("id")}
    if message_type == "file":
        return {
            "type": "file",
            "file_id": line_message.get("id"),
            "file_name": line_message.get("fileName"),
        }
    return {"type": message_type or "unknown"}


def parse_line_message(event):
    source = event.get("source", {})
    line_message = event.get("message", {})
    return {
        "message_id": generate_short_id("m"),
        "from": normalize_user_id(source.get("userId")),
        "to": AGENT_ID,
        "content": [parse_content_item(line_message)],
        "created_at": iso_now(),
    }


def insert_message_to_supabase(message_obj):
    payload = {
        "message_id": message_obj["message_id"],
        "from_id": message_obj["from"],
        "to_id": message_obj["to"],
        "content": message_obj["content"],
        "created_at": message_obj["created_at"],
    }

    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/messages"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()


def build_inspect_reply(message_obj):
    content_types = ", ".join(item.get("type", "unknown") for item in message_obj["content"])
    return (
        f"from: {message_obj['from']}\n"
        f"to: {message_obj['to']}\n"
        f"content_types: {content_types}"
    )[:1000]


def reply_line(reply_token, text):
    if not reply_token:
        return

    if not LINE_CHANNEL_ACCESS_TOKEN:
        raise RuntimeError("Missing required environment variables: LINE_CHANNEL_ACCESS_TOKEN")

    response = requests.post(
        "https://api.line.me/v2/bot/message/reply",
        headers={
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text[:1500]}],
        },
        timeout=10,
    )
    response.raise_for_status()


def build_non_text_reply(message_obj):
    content_type = message_obj["content"][0].get("type", "unknown")
    return f"已收到非文字訊息（{content_type}）。"


def handle_echo(event, message_obj):
    reply_token = event.get("replyToken")
    if not reply_token:
        return

    content_item = message_obj["content"][0]
    if content_item.get("type") != "text":
        reply_line(reply_token, build_non_text_reply(message_obj))
        return

    text = content_item.get("text")
    if not text:
        return

    reply_line(reply_token, text)


def handle_inspect(event, message_obj):
    if INSPECT_WRITE_SUPABASE:
        try:
            insert_message_to_supabase(message_obj)
        except Exception as exc:
            print(f"Supabase insert failed in inspect mode: {exc}")

    reply_token = event.get("replyToken")
    if not reply_token:
        return

    reply_line(reply_token, build_inspect_reply(message_obj))


def call_direct_gpt(user_text):
    if not openai_client:
        raise RuntimeError("Missing required environment variables: OPENAI_API_KEY")

    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )
    return (response.output_text or "").strip()[:1500]


def handle_direct_gpt(event, message_obj):
    try:
        insert_message_to_supabase(message_obj)
    except Exception as exc:
        # Insert failure should be logged, but should not crash the webhook.
        print(f"Supabase insert failed in direct_gpt mode: {exc}")

    reply_token = event.get("replyToken")
    if not reply_token:
        return

    content_item = message_obj["content"][0]
    if content_item.get("type") != "text":
        reply_line(reply_token, build_non_text_reply(message_obj))
        return

    user_text = content_item.get("text")
    if not user_text:
        return

    try:
        answer = call_direct_gpt(user_text)
        if not answer:
            answer = "目前沒有產生回覆，請稍後再試。"
    except Exception as exc:
        print(f"OpenAI call failed: {exc}")
        answer = "目前暫時無法處理這則訊息，請稍後再試。"

    reply_line(reply_token, answer)


def process_event(event):
    if event.get("type") != "message":
        return

    message_obj = parse_line_message(event)

    if APP_MODE == "echo":
        handle_echo(event, message_obj)
        return

    if APP_MODE == "inspect":
        handle_inspect(event, message_obj)
        return

    if APP_MODE == "direct_gpt":
        handle_direct_gpt(event, message_obj)
        return

    raise RuntimeError(f"Unsupported APP_MODE: {APP_MODE}")


def validate_mode_requirements():
    if APP_MODE == "echo":
        return require_env_vars(["LINE_CHANNEL_ACCESS_TOKEN"])

    if APP_MODE == "inspect":
        required = ["LINE_CHANNEL_ACCESS_TOKEN"]
        if INSPECT_WRITE_SUPABASE:
            required.extend(["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"])
        return require_env_vars(required)

    if APP_MODE == "direct_gpt":
        return require_env_vars(
            [
                "LINE_CHANNEL_ACCESS_TOKEN",
                "OPENAI_API_KEY",
                "SUPABASE_URL",
                "SUPABASE_SERVICE_ROLE_KEY",
            ]
        )

    return f"Unsupported APP_MODE: {APP_MODE}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path not in {"/", "/api"}:
            error_response(self, 404, "not_found")
            return

        error = validate_mode_requirements()
        if error:
            error_response(self, 500, error)
            return

        send_json(self, 200, {"ok": True, "mode": APP_MODE})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in {"/", "/api"}:
            error_response(self, 404, "not_found")
            return

        error = validate_mode_requirements()
        if error:
            error_response(self, 500, error)
            return

        try:
            body = parse_json_request(self)
        except Exception:
            error_response(self, 400, "invalid_json")
            return

        try:
            for event in body.get("events", []):
                process_event(event)
        except Exception as exc:
            print(f"Webhook processing failed: {exc}")
            error_response(self, 500, "internal_error")
            return

        send_json(self, 200, {"ok": True, "mode": APP_MODE})
