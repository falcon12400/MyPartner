import os
import json
import requests
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

def handler(request):
    if request.method == "GET":
        return {
            "statusCode": 200,
            "body": "webhook running"
        }

    body = request.get_json()

    events = body.get("events", [])

    for event in events:
        if event.get("type") != "message":
            continue
        if event["message"]["type"] != "text":
            continue

        user_text = event["message"]["text"]
        reply_token = event["replyToken"]

        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=user_text
        )

        answer = resp.output_text[:2000]

        headers = {
            "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "replyToken": reply_token,
            "messages":[
                {
                    "type":"text",
                    "text":answer
                }
            ]
        }

        requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=payload
        )

    return {
        "statusCode":200,
        "body":"ok"
    }
