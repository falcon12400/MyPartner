# Vercel

---

## 這是什麼

Vercel 是本系統的「入口伺服器」。

負責接收來自 LINE 的 webhook，並根據設定執行對應的處理邏輯。

---

## 在系統中的角色

~~~text
LINE → Vercel →（依模式處理）→ OpenAI / Supabase
~~~

Vercel 負責：

- 接收 LINE 訊息（webhook）
- 解析訊息格式
- 根據 APP_MODE 決定行為
- 呼叫 OpenAI（在 direct_gpt 模式）
- 寫入 Supabase（依設定）
- 回覆 LINE

---

## 需要維護什麼

日常會需要調整的項目：

- 環境變數（APP_MODE 等）
- webhook 行為（程式邏輯）
- API key（OpenAI / LINE / Supabase）
- 部署版本（deploy / redeploy）

---

## 常用操作

### 1️⃣ 修改系統模式

~~~text
APP_MODE=echo / inspect / direct_gpt
~~~

👉 用來切換系統行為

---

### 2️⃣ 重新部署（重要）

當你修改：

- 環境變數
- 程式碼

都需要：

~~~text
Deployments → Redeploy
~~~

否則變更不會生效

---

### 3️⃣ 查看執行狀態

在 Vercel 可查看：

- function logs
- request logs
- error 訊息

👉 用於 debug

---

## 設定說明

目前主要使用以下環境變數：

### APP_MODE

~~~text
APP_MODE=echo / inspect / direct_gpt
~~~

👉 控制系統運作模式  
👉 詳細說明請參考：

~~~text
docs/modes.md
~~~

---

### SAVE_ASSISTANT_REPLY

~~~text
SAVE_ASSISTANT_REPLY=true / false
~~~

👉 控制是否儲存 AI 回覆

---

### ENABLE_INSPECT_INSERT

~~~text
ENABLE_INSPECT_INSERT=true / false
~~~

👉 控制 inspect 模式是否寫入資料庫

---

## 測試方式

### 方法 1：基本測試

~~~text
APP_MODE=echo
~~~

👉 LINE 傳訊 → 應原樣回覆

---

### 方法 2：結構測試

~~~text
APP_MODE=inspect
ENABLE_INSPECT_INSERT=true
~~~

👉 檢查：

- 回覆內容是否正確
- Supabase 是否有資料

---

### 方法 3：完整測試

~~~text
APP_MODE=direct_gpt
SAVE_ASSISTANT_REPLY=true
~~~

👉 檢查：

- LINE 是否回 AI
- 資料庫是否有完整對話

---

## 常見問題

### ❓ 改了環境變數但沒反應

原因：

- 沒有 redeploy

解法：

~~~text
Deployments → Redeploy
~~~

---

### ❓ LINE 沒有回應

可能原因：

- webhook 壞掉
- APP_MODE 設錯
- token 錯誤

建議：

1. 先切換：

~~~text
APP_MODE=echo
~~~

2. 確認是否有回應

---

### ❓ 有回應但不是 AI

原因：

- APP_MODE 不是 direct_gpt

---

### ❓ inspect 沒寫入資料庫

原因：

- ENABLE_INSPECT_INSERT=false

---

### ❓ direct_gpt 沒存 AI 回覆

原因：

- SAVE_ASSISTANT_REPLY=false

---

## 一句話理解

👉 Vercel 是整個系統的「控制中心與入口」
