from http.server import BaseHTTPRequestHandler
import json
import os
import requests
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("webhook running".encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"invalid json")
            return

        events = body.get("events", [])

        for event in events:
            if event.get("type") != "message":
                continue

            message = event.get("message", {})
            if message.get("type") != "text":
                continue

            user_text = message.get("text", "")
            reply_token = event.get("replyToken")

            if not reply_token:
                continue

            resp = client.responses.create(
                model="gpt-4.1-mini",
                input=[
                    {"role": "system", "content": "你是 LINE 助手，請用繁體中文簡潔回覆。"},
                    {"role": "user", "content": user_text}
                ]
            )

            answer = resp.output_text[:2000]

            headers = {
                "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }

            payload = {
                "replyToken": reply_token,
                "messages": [
                    {
                        "type": "text",
                        "text": answer
                    }
                ]
            }

            requests.post(
                "https://api.line.me/v2/bot/message/reply",
                headers=headers,
                json=payload,
                timeout=10
            )

        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")
