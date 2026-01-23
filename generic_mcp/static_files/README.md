# Static Files 說明

此資料夾用於存放 MCP Server 所需的靜態檔案（如 API 憑證）。

## Gmail API 憑證

請將以下檔案放到此資料夾：

1. **credentials.json** - 從 Google Cloud Console 下載的 OAuth 2.0 憑證
2. **gmail_token.json** - 首次 OAuth 授權後自動產生（不需手動建立）

## 安全注意事項

⚠️ 這些檔案包含敏感資訊，請勿提交到 Git 或分享給他人。

`.gitignore` 已設定忽略這些檔案。

## 設定步驟

請參考 [Gmail API 設定指南](../../docs/GMAIL_API_SETUP.md)
