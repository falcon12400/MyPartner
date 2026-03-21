# MyPartner LINE AI Webhook

本專案是一個透過 LINE 傳訊息，由 AI 自動回應並儲存資料的系統。

👉 核心用途：建立「LINE × AI × 資料庫」的訊息入口  
👉 可擴充為 agent / worker / 任務系統

---

## 系統組成（Components Overview）

~~~text
- Vercel：接收 LINE webhook，負責主要邏輯
- LINE：使用者傳送訊息的入口
- OpenAI：產生 AI 回覆
- Supabase：儲存訊息資料
~~~

---

## 快速開始（Quick Start）

~~~text
1. 設定環境變數
2. 重新部署（Redeploy）
3. 傳送 LINE 訊息測試
~~~

👉 詳細使用方式請參考 docs

---

## 文件索引（Documentation）

- [Vercel（webhook 與環境變數）](docs/vercel.md)
- [LINE 設定](docs/line.md)
- [OpenAI 設定](docs/openai.md)
- [Supabase 設定](docs/supabase.md)
- [系統模式（APP_MODE）](docs/modes.md)


---

## 系統定位

~~~text
LINE → webhook → AI → database
~~~

👉 現在是 chatbot  
👉 未來可擴充為 agent 系統

---

## 一句話理解

👉 一個可擴充的 AI 訊息入口系統
