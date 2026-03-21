# MyPartner LINE AI Webhook

本專案是一個部署在 Vercel 的 LINE Messaging API webhook，結合 OpenAI 與 Supabase，提供可切換模式的訊息處理系統。設計目標是建立一個「可擴充的訊息入口」，未來可延伸為多 agent、任務系統與本機 worker 架構。

---

## 一、系統架構概念

目前版本為 MVP（最小可行版本），資料流如下：

LINE 使用者  
→ LINE Messaging API  
→ Vercel webhook（本專案）  
→（依模式決定）  
→ OpenAI / Supabase  
→ 回覆 LINE

未來可擴充為：

LINE → webhook → Supabase → worker（本機）→ 回寫結果 → LINE

---

## 二、專案功能

本專案具備三種運作模式：

1. echo（測試）
2. inspect（除錯）
3. direct_gpt（正式 AI 回覆）

並支援：

- LINE 訊息接收
- OpenAI 回覆
- Supabase 訊息儲存（JSONB）
- assistant 回覆可選擇是否儲存
- 統一 message schema（未來可擴充 agent / task）

---

## 三、Message Schema（核心設計）

所有訊息會轉換為以下格式：

```json
{
  "message_id": "m_XXXXXXXX",
  "from": "u_XXXXXXXX",
  "to": "a_main",
  "content": [
    { "type": "text", "text": "..." }
  ],
  "created_at": "ISO8601"
}

說明：
	•	message_id：唯一 ID
	•	from：訊息來源（user 或 agent）
	•	to：接收對象（目前固定 a_main）
	•	content：支援多種格式（text / image / audio / video / file）
	•	created_at：時間戳記

⸻

四、Vercel 部署方式

1. 專案結構

api/
  index.py
requirements.txt

Vercel 會自動將 /api/index.py 當作：

https://你的網址/api


⸻

2. 部署流程
	1.	將專案 push 到 GitHub
	2.	在 Vercel 建立新 project
	3.	選擇該 repository
	4.	Deploy

⸻

3. Environment Variables（非常重要）

請在 Vercel → Project → Settings → Environment Variables 設定：

OPENAI_API_KEY=sk-xxxx
LINE_CHANNEL_ACCESS_TOKEN=xxxx
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=xxxx

APP_MODE=echo
SAVE_ASSISTANT_REPLY=true
ENABLE_INSPECT_INSERT=true


⸻

4. 修改後需重新部署

任何環境變數變更後：

Deployments → Redeploy

否則不會生效

⸻

五、APP_MODE 說明

echo

APP_MODE=echo

行為：
	•	收到什麼回什麼
	•	不使用 OpenAI
	•	不寫入資料庫

用途：
	•	測試 webhook 是否正常

⸻

inspect

APP_MODE=inspect
ENABLE_INSPECT_INSERT=true

行為：
	•	回傳解析結果
	•	可選擇寫入 Supabase

回覆範例：

mode=inspect
from=u_xxxxxxxx
to=a_main
message_id=m_xxxxxxxx
content_types=text
preview=你好

用途：
	•	驗證 message schema
	•	除錯

⸻

direct_gpt（正式模式）

APP_MODE=direct_gpt

行為：
	1.	儲存 user message
	2.	呼叫 OpenAI
	3.	回覆 LINE
4.（可選）儲存 assistant 回覆

⸻

六、SAVE_ASSISTANT_REPLY

SAVE_ASSISTANT_REPLY=true

true（建議）
	•	user 訊息 → 存
	•	assistant 回覆 → 也存

優點：
	•	可還原完整對話
	•	可做記憶 / 分析 / debug

⸻

false
	•	只存 user 訊息
	•	不存 AI 回覆

用途：
	•	測試
	•	減少資料量

⸻

七、Supabase 設定

需建立一張 table：

create table messages (
  id bigint generated always as identity primary key,
  message_id text unique not null,
  from_id text not null,
  to_id text not null,
  content jsonb not null,
  created_at timestamptz default now()
);


⸻

八、測試流程（建議順序）

Step 1：測試 webhook

APP_MODE=echo

LINE 傳訊息 → 應原樣回覆

⸻

Step 2：測試資料結構

APP_MODE=inspect
ENABLE_INSPECT_INSERT=true

→ 檢查 Supabase 是否有資料

⸻

Step 3：啟用 AI

APP_MODE=direct_gpt
SAVE_ASSISTANT_REPLY=true

→ LINE 應回 GPT 回覆
→ Supabase 應有完整對話

⸻

九、目前限制
	•	webhook 為同步處理（blocking）
	•	尚未支援 task / worker
	•	尚未支援多 agent routing
	•	尚未支援檔案下載（僅記錄 file_id）

⸻

十、未來擴充方向
	•	worker（本機或雲端）
	•	任務系統（task queue）
	•	agent 分工（research / planner / executor）
	•	realtime（取代 polling）
	•	多輪對話記憶

⸻

十一、一句話理解整個專案

這是一個：

👉「LINE → AI → 資料庫」的可擴充入口系統
👉 現在是 chatbot，未來可以變成 agent 平台

