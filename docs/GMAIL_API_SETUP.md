# Gmail API 設定指南

本文件說明如何在 Google Cloud Platform (GCP) 設定 Gmail API，讓 MCP Server 能夠發送郵件。

---

## 📋 目錄

1. [建立 GCP 專案](#1-建立-gcp-專案)
2. [啟用 Gmail API](#2-啟用-gmail-api)
3. [設定 OAuth 同意畫面](#3-設定-oauth-同意畫面)
4. [建立 OAuth 憑證](#4-建立-oauth-憑證)
5. [新增測試使用者](#5-新增測試使用者-重要)
6. [下載並放置憑證](#6-下載並放置憑證)
7. [首次授權](#7-首次授權)

---

## 1. 建立 GCP 專案

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)

2. 點擊頁面頂部的專案選擇器（Project Selector）

3. 點擊「**新增專案**」（New Project）

4. 填寫專案資訊：
   - **專案名稱**：例如 `MCP Gmail Service`
   - **機構**：選擇您的機構（或保持預設）

5. 點擊「**建立**」

6. 等待專案建立完成後，確認已切換到新專案

---

## 2. 啟用 Gmail API

1. 在 GCP Console 左側選單，點擊「**API 和服務**」→「**程式庫**」
   
   或直接前往：https://console.cloud.google.com/apis/library

2. 在搜尋框輸入 `Gmail API`

3. 點擊「**Gmail API**」

4. 點擊「**啟用**」按鈕

5. 等待 API 啟用完成

---

## 3. 設定 OAuth 同意畫面

> ⚠️ **重要**：必須先完成此步驟才能建立 OAuth 憑證

1. 在左側選單，點擊「**API 和服務**」→「**OAuth 同意畫面**」

   或直接前往：https://console.cloud.google.com/apis/credentials/consent

2. 選擇使用者類型：
   - **External**：適用於一般 Gmail 帳號（推薦）
   - **Internal**：僅適用於 Google Workspace 組織內部
   
   點擊「**建立**」

3. 填寫「**OAuth 同意畫面**」資訊：

   | 欄位 | 填寫內容 |
   |------|----------|
   | 應用程式名稱 | `MCP Gmail Service`（或自訂名稱） |
   | 使用者支援電子郵件 | 選擇您的 email |
   | 應用程式標誌 | （可選，跳過） |
   | 應用程式首頁 | （可選，跳過） |
   | 應用程式隱私權政策連結 | （可選，跳過） |
   | 應用程式服務條款連結 | （可選，跳過） |
   | 授權網域 | （可選，跳過） |
   | 開發人員聯絡資訊 | 填寫您的 email |

4. 點擊「**儲存並繼續**」

5. 在「**範圍**」(Scopes) 頁面：
   - 點擊「**新增或移除範圍**」
   - 搜尋並勾選以下範圍：
     - `https://www.googleapis.com/auth/gmail.send`
     - `https://www.googleapis.com/auth/gmail.readonly`
   - 點擊「**更新**」
   - 點擊「**儲存並繼續**」

6. 進入「**測試使用者**」頁面（下一節詳述）

---

## 4. 建立 OAuth 憑證

1. 在左側選單，點擊「**API 和服務**」→「**憑證**」

   或直接前往：https://console.cloud.google.com/apis/credentials

2. 點擊頁面頂部的「**+ 建立憑證**」

3. 選擇「**OAuth 用戶端 ID**」

4. 設定 OAuth 用戶端：

   | 欄位 | 選擇/填寫 |
   |------|----------|
   | 應用程式類型 | **電腦版應用程式** (Desktop app) |
   | 名稱 | `MCP Gmail Client`（或自訂名稱） |

5. 點擊「**建立**」

6. 會顯示您的用戶端 ID 和密碼，點擊「**下載 JSON**」

7. 點擊「**確定**」關閉對話框

---

## 5. 新增測試使用者（重要！）

> ⚠️ **非常重要**：如果您的應用程式處於「測試」狀態（未發布），只有被加入為「測試使用者」的 Google 帳號才能使用 OAuth 授權。否則會看到「Access blocked: This app's request is invalid」錯誤。

1. 前往「**OAuth 同意畫面**」

   https://console.cloud.google.com/apis/credentials/consent

2. 點擊左側的「**OAuth 同意畫面**」

3. 向下捲動到「**測試使用者**」區塊

4. 點擊「**+ ADD USERS**」

5. 輸入要授權的 Gmail 帳號（您要用來發送郵件的帳號）

   例如：`your-email@gmail.com`

6. 點擊「**新增**」

7. 點擊「**儲存**」

### 確認測試使用者已新增

您應該會看到類似以下畫面：

```
測試使用者
+--------------------------+
| your-email@gmail.com     |
+--------------------------+
```

---

## 6. 下載並放置憑證

1. 找到剛才下載的 JSON 檔案
   - 通常名稱類似：`client_secret_XXXXX.apps.googleusercontent.com.json`

2. 將檔案重新命名為：`credentials.json`

3. 將 `credentials.json` 放到 `static_files` 目錄：
   ```
   swagger_mcp_service/
   └── generic_mcp/
       ├── gmail_server.py
       ├── static_files/
       │   └── credentials.json  ← 放這裡
       └── ...
   ```

---

## 7. 首次授權

1. 執行 Gmail MCP Server：
   ```bash
   cd /path/to/swagger_mcp_service
   python generic_mcp/gmail_server.py
   ```

2. 程式會自動開啟瀏覽器，顯示 Google 登入頁面

3. 選擇您在「測試使用者」中新增的 Google 帳號

4. 您可能會看到警告「Google hasn't verified this app」：
   - 點擊「**Advanced**」（進階）
   - 點擊「**Go to MCP Gmail Service (unsafe)**」

5. 點擊「**Continue**」或「**Allow**」授權應用程式存取 Gmail

6. 授權成功後，瀏覽器會顯示「The authentication flow has completed」

7. 程式會自動儲存 token 到 `gmail_token.json`，之後不需要再授權

---

## 🔧 常見問題

### Q: 出現「Access blocked: This app's request is invalid」

**A:** 您使用的 Google 帳號沒有被加入測試使用者。請回到步驟 5 新增您的帳號。

### Q: 出現「Error 403: access_denied」

**A:** 
1. 確認 Gmail API 已啟用
2. 確認測試使用者已正確新增
3. 確認使用正確的 Google 帳號登入

### Q: Token 過期怎麼辦？

**A:** 程式會自動刷新 token。如果遇到問題，刪除 `gmail_token.json` 重新授權即可。

### Q: 如何正式發布應用程式？

**A:** 
1. 前往 OAuth 同意畫面
2. 點擊「**發布應用程式**」
3. 完成 Google 的驗證程序（可能需要數天到數週）
4. 發布後所有 Google 帳號都可以使用

---

## 📁 檔案結構

設定完成後，您的目錄結構應該如下：

```
swagger_mcp_service/
└── generic_mcp/
    ├── gmail_server.py      # Gmail MCP Server
    ├── config.yaml          # MCP 設定檔
    └── static_files/        # 靜態檔案資料夾
        ├── credentials.json     # OAuth 憑證（從 GCP 下載）
        └── gmail_token.json     # 授權 Token（首次授權後自動產生）
```

---

## ✅ 驗證設定

執行以下命令測試 Gmail MCP Server：

```bash
python generic_mcp/gmail_server.py
```

成功輸出：
```
==================================================
🚀 Gmail MCP Server 啟動中...
==================================================
✅ Gmail 認證成功: your-email@gmail.com
📧 Gmail MCP Server 已準備就緒
==================================================
```

---

## 🔗 相關連結

- [Google Cloud Console](https://console.cloud.google.com/)
- [Gmail API 文件](https://developers.google.com/gmail/api)
- [OAuth 2.0 說明](https://developers.google.com/identity/protocols/oauth2)
