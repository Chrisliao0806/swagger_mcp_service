"""
Gmail MCP Server
透過 Gmail API 發送郵件的 MCP Server

使用前需要：
1. 在 Google Cloud Console 建立專案並啟用 Gmail API
2. 建立 OAuth 2.0 憑證（桌面應用程式類型）
3. 下載 credentials.json 放到 generic_mcp/static_files/ 目錄
4. 第一次執行時會開啟瀏覽器進行 OAuth 授權
"""

import os
import sys
import json
import base64
import logging
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List

from mcp.server.fastmcp import FastMCP
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Gmail API access scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# access static files path*(generic_mcp/static_files)*
STATIC_FILES_DIR = Path(__file__).parent / "static_files"
STATIC_FILES_DIR.mkdir(exist_ok=True)
CREDENTIALS_FILE = STATIC_FILES_DIR / "credentials.json"
TOKEN_FILE = STATIC_FILES_DIR / "gmail_token.json"


class GmailService:
    """Gmail API 服務封裝"""

    def __init__(self):
        self.service = None
        self.user_email = None
        self._authenticate()

    def _authenticate(self):
        """進行 OAuth2 認證"""
        creds = None

        # 檢查是否有已存在的 token
        if TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            except Exception as e:
                logger.warning("載入 token 失敗: %s", e)

        # 如果沒有有效的 token，進行授權流程
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning("刷新 token 失敗: %s", e)
                    creds = None

            if not creds:
                if not CREDENTIALS_FILE.exists():
                    raise FileNotFoundError(
                        f"找不到 credentials.json！\n"
                        f"請從 Google Cloud Console 下載 OAuth 2.0 憑證並放到: {CREDENTIALS_FILE}"
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # 儲存 token
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())
            logger.info("Token 已儲存到: %s", TOKEN_FILE)

        # 建立 Gmail 服務
        self.service = build("gmail", "v1", credentials=creds)

        # 取得使用者 email
        profile = self.service.users().getProfile(userId="me").execute()
        self.user_email = profile.get("emailAddress")
        logger.info("已登入 Gmail: %s", self.user_email)

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        html: bool = False,
    ) -> dict:
        """
        發送郵件

        Args:
            to: 收件人 email（多個收件人用逗號分隔）
            subject: 郵件主旨
            body: 郵件內容
            cc: 副本收件人（可選，多個用逗號分隔）
            bcc: 密件副本收件人（可選，多個用逗號分隔）
            html: 是否為 HTML 格式（預設 False）

        Returns:
            發送結果
        """
        try:
            # 建立郵件
            if html:
                message = MIMEMultipart("alternative")
                message.attach(MIMEText(body, "html", "utf-8"))
            else:
                message = MIMEText(body, "plain", "utf-8")

            message["to"] = to
            message["from"] = self.user_email
            message["subject"] = subject

            if cc:
                message["cc"] = cc
            if bcc:
                message["bcc"] = bcc

            # 編碼郵件
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # 發送郵件
            result = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": encoded_message})
                .execute()
            )

            logger.info("郵件已發送，Message ID: %s", result["id"])
            return {
                "success": True,
                "message_id": result["id"],
                "to": to,
                "subject": subject,
                "from": self.user_email,
            }

        except HttpError as e:
            logger.error("發送郵件失敗: %s", e)
            return {"success": False, "error": str(e)}

    def get_profile(self) -> dict:
        """取得使用者 Gmail 資訊"""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return {
                "success": True,
                "email": profile.get("emailAddress"),
                "messages_total": profile.get("messagesTotal"),
                "threads_total": profile.get("threadsTotal"),
                "history_id": profile.get("historyId"),
            }
        except HttpError as e:
            return {"success": False, "error": str(e)}

    def list_labels(self) -> dict:
        """列出所有標籤"""
        try:
            results = self.service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])
            return {
                "success": True,
                "labels": [{"id": l["id"], "name": l["name"]} for l in labels],
            }
        except HttpError as e:
            return {"success": False, "error": str(e)}


# 建立 MCP Server
mcp = FastMCP("Gmail MCP Server")

# 初始化 Gmail 服務（延遲初始化）
gmail_service: Optional[GmailService] = None


def get_gmail_service() -> GmailService:
    """取得 Gmail 服務實例"""
    global gmail_service
    if gmail_service is None:
        gmail_service = GmailService()
    return gmail_service


@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = None,
    bcc: str = None,
    html: bool = False,
) -> str:
    """
    透過 Gmail 發送郵件

    Args:
        to: 收件人 email 地址（多個收件人請用逗號分隔，例如：user1@example.com, user2@example.com）
        subject: 郵件主旨
        body: 郵件內容（純文字或 HTML）
        cc: 副本收件人（可選，多個用逗號分隔）
        bcc: 密件副本收件人（可選，多個用逗號分隔）
        html: 內容是否為 HTML 格式（預設為純文字）
    """
    service = get_gmail_service()
    result = service.send_email(
        to=to, subject=subject, body=body, cc=cc, bcc=bcc, html=html
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_gmail_profile() -> str:
    """
    取得目前登入的 Gmail 帳號資訊

    回傳內容包含：
    - email: 電子郵件地址
    - messages_total: 總郵件數
    - threads_total: 總對話串數
    """
    service = get_gmail_service()
    result = service.get_profile()
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_gmail_labels() -> str:
    """
    列出 Gmail 信箱中的所有標籤（資料夾）

    可用於了解信箱的組織結構
    """
    service = get_gmail_service()
    result = service.list_labels()
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def draft_email(to: str, subject: str, body: str, cc: str = None) -> str:
    """
    預覽郵件內容（不實際發送）

    用於在發送前確認郵件內容是否正確

    Args:
        to: 收件人 email 地址
        subject: 郵件主旨
        body: 郵件內容
        cc: 副本收件人（可選）
    """
    service = get_gmail_service()

    preview = {
        "action": "預覽（尚未發送）",
        "from": service.user_email,
        "to": to,
        "cc": cc,
        "subject": subject,
        "body": body[:500] + "..." if len(body) > 500 else body,
        "body_length": len(body),
        "hint": "確認內容無誤後，請使用 send_email 工具發送郵件",
    }
    return json.dumps(preview, ensure_ascii=False, indent=2)


def main():
    """主程式入口"""
    logger.info("=" * 50)
    logger.info("Gmail MCP Server 啟動中...")
    logger.info("=" * 50)

    # 預先進行認證（確保 token 有效）
    try:
        service = get_gmail_service()
        logger.info("Gmail 認證成功: %s", service.user_email)
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Gmail 認證失敗: %s", e)
        sys.exit(1)

    logger.info("📧 Gmail MCP Server 已準備就緒")
    logger.info("=" * 50)

    # 啟動 MCP Server
    mcp.run()


if __name__ == "__main__":
    main()
