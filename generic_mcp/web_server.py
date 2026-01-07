"""
Generic MCP Web Server
提供漂亮的網頁聊天介面，支援 Streaming 回應
"""

import asyncio
import os
import sys
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncGenerator
from contextlib import AsyncExitStack
from dotenv import load_dotenv

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from langchain_openai import ChatOpenAI
from langchain_mcp import MCPToolkit
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openapi_parser import OpenAPIParser, load_config

# 抑制 MCP client 的 JSONRPC 解析警告
logging.getLogger("mcp.client.stdio").setLevel(logging.ERROR)


def setup_logging():
    """設定 logging 格式"""

    # 建立自定義格式
    class ColoredFormatter(logging.Formatter):
        """帶顏色的 log 格式"""

        COLORS = {
            "DEBUG": "\033[36m",  # Cyan
            "INFO": "\033[32m",  # Green
            "WARNING": "\033[33m",  # Yellow
            "ERROR": "\033[31m",  # Red
            "CRITICAL": "\033[35m",  # Magenta
        }
        RESET = "\033[0m"

        def format(self, record):
            color = self.COLORS.get(record.levelname, self.RESET)
            record.levelname = f"{color}{record.levelname}{self.RESET}"
            record.msg = f"{color}{record.msg}{self.RESET}"
            return super().format(record)

    # 設定 root logger
    handler = logging.StreamHandler()
    handler.setFormatter(
        ColoredFormatter(
            fmt="%(asctime)s │ %(levelname)-17s │ %(name)s │ %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # 設定 logger
    logger = logging.getLogger("mcp_web")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False

    return logger


# 設定 logger
logger = setup_logging()


class MCPWebServer:
    """MCP 網頁聊天伺服器"""

    def __init__(self, config_path: str = None):
        """初始化"""
        load_dotenv()

        self.config = load_config(config_path)
        self.config_path = config_path or str(Path(__file__).parent / "config.yaml")

        # 解析 MCP servers 設定
        self.mcp_servers = self._parse_mcp_servers()

        # 連接狀態
        self.connected_servers: List[Dict[str, Any]] = []
        self.openapi_tools_summary: str = ""
        self.all_tools: List = []
        self.agent = None
        self.llm = None

        # 對話 sessions（每個 session_id 對應一組對話歷史）
        self.sessions: Dict[str, List] = {}

        # AsyncExitStack（需要在整個生命週期保持開啟）
        self.stack: Optional[AsyncExitStack] = None

        # FastAPI app
        self.app = FastAPI(title="MCP Chat", description="MCP 智慧聊天助手")
        self._setup_routes()
        self._setup_middleware()

    def _parse_mcp_servers(self) -> List[Dict[str, Any]]:
        """解析 MCP servers 設定"""
        servers = []
        if "mcp_servers" in self.config:
            for server_config in self.config["mcp_servers"]:
                if server_config.get("enabled", True):
                    servers.append(server_config)
        elif "api" in self.config:
            servers.append(
                {
                    "name": self.config.get("mcp_server", {}).get("name", "API"),
                    "type": "openapi",
                    "enabled": True,
                    "openapi": self.config["api"],
                    "tool_generation": self.config.get("tool_generation", {}),
                }
            )
        return servers

    def _setup_middleware(self):
        """設定 CORS 中間件"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_routes(self):
        """設定路由"""

        # 取得模板路徑
        templates_dir = Path(__file__).parent / "templates"

        @self.app.get("/", response_class=HTMLResponse)
        async def index():
            """主頁面"""
            logger.info("📄 請求首頁")
            html_path = templates_dir / "index.html"
            if html_path.exists():
                return html_path.read_text(encoding="utf-8")
            else:
                logger.error("找不到模板檔案: %s", html_path)
                raise HTTPException(status_code=500, detail="找不到頁面模板")

        @self.app.get("/api/status")
        async def status():
            """取得伺服器狀態"""
            logger.debug("🔍 查詢伺服器狀態")
            return {
                "connected": len(self.connected_servers) > 0,
                "servers": self.connected_servers,
                "total_tools": len(self.all_tools),
            }

        @self.app.post("/api/session")
        async def create_session():
            """建立新的聊天 session"""
            session_id = str(uuid.uuid4())
            system_prompt = self._generate_system_prompt()
            self.sessions[session_id] = [SystemMessage(content=system_prompt)]
            logger.info("🆕 建立新 Session: %s...", session_id[:8])
            return {"session_id": session_id}

        @self.app.delete("/api/session/{session_id}")
        async def delete_session(session_id: str):
            """刪除聊天 session"""
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info("🗑️  刪除 Session: %s...", session_id[:8])
            return {"status": "ok"}

        @self.app.post("/api/chat/{session_id}")
        async def chat(session_id: str, request: Request):
            """處理聊天訊息（Streaming）"""
            if not self.agent:
                logger.error("❌ Agent 尚未初始化")
                raise HTTPException(status_code=503, detail="Agent 尚未初始化")

            body = await request.json()
            user_message = body.get("message", "").strip()

            if not user_message:
                raise HTTPException(status_code=400, detail="訊息不能為空")

            # 取得或建立 session
            if session_id not in self.sessions:
                system_prompt = self._generate_system_prompt()
                self.sessions[session_id] = [SystemMessage(content=system_prompt)]
                logger.info("🆕 自動建立 Session: %s...", session_id[:8])

            messages = self.sessions[session_id]
            messages.append(HumanMessage(content=user_message))

            # 記錄使用者訊息
            user_msg_preview = (
                user_message[:50] + "..." if len(user_message) > 50 else user_message
            )
            logger.info("💬 [Session %s] 使用者: %s", session_id[:8], user_msg_preview)

            return StreamingResponse(
                self._stream_response(session_id, messages),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        @self.app.get("/api/tools")
        async def list_tools():
            """列出所有可用工具"""
            logger.debug("📋 查詢工具列表，共 %d 個", len(self.all_tools))
            tools_info = []
            for tool in self.all_tools:
                tools_info.append(
                    {
                        "name": tool.name,
                        "description": tool.description[:200]
                        if tool.description
                        else "",
                    }
                )
            return {"tools": tools_info}

    async def _stream_response(
        self, session_id: str, messages: List
    ) -> AsyncGenerator[str, None]:
        """產生 streaming 回應"""
        start_time = datetime.now()
        token_count = 0

        try:
            # 使用 astream_events 來獲取 streaming 回應
            full_response = ""
            tool_calls = []

            logger.debug("🚀 [Session %s] 開始 streaming 回應...", session_id[:8])

            async for event in self.agent.astream_events(
                {"messages": messages}, version="v2"
            ):
                kind = event.get("event", "")

                # 處理 LLM streaming token
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        if isinstance(content, str):
                            full_response += content
                            token_count += 1
                            # 發送 SSE 事件
                            yield f"data: {json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"

                # 處理工具呼叫開始
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    logger.info(
                        "🔧 [Session %s] 呼叫工具: %s", session_id[:8], tool_name
                    )
                    input_preview = json.dumps(tool_input, ensure_ascii=False)[:100]
                    logger.debug("   └─ 輸入參數: %s...", input_preview)
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': tool_name, 'input': tool_input}, ensure_ascii=False)}\n\n"

                # 處理工具呼叫結束
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    output_preview = (
                        str(tool_output)[:100] + "..."
                        if len(str(tool_output)) > 100
                        else str(tool_output)
                    )
                    logger.info(
                        "✅ [Session %s] 工具完成: %s", session_id[:8], tool_name
                    )
                    logger.debug("   └─ 輸出結果: %s", output_preview)
                    # 傳送完整的工具輸出（前端可自行決定如何顯示）
                    yield f"data: {json.dumps({'type': 'tool_end', 'name': tool_name, 'output': str(tool_output)}, ensure_ascii=False)}\n\n"

            # 更新對話歷史
            if full_response:
                messages.append(AIMessage(content=full_response))
                self.sessions[session_id] = messages

            # 計算耗時
            elapsed = (datetime.now() - start_time).total_seconds()
            response_preview = (
                full_response[:80] + "..." if len(full_response) > 80 else full_response
            )
            logger.info(
                "🤖 [Session %s] 助手回覆 (%.2fs, ~%d tokens)",
                session_id[:8],
                elapsed,
                token_count,
            )
            logger.debug("   └─ 內容: %s", response_preview)

            # 發送結束事件
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error("❌ [Session %s] Streaming 錯誤: %s", session_id[:8], e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    def _expand_env_vars(self, value: Any) -> Any:
        """展開環境變數"""
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            return os.getenv(env_var, "")
        return value

    def _build_openapi_config(self, server_config: Dict[str, Any]) -> Dict[str, Any]:
        """為 OpenAPI server 建構完整設定"""
        openapi_config = server_config.get("openapi", {})
        tool_gen_config = server_config.get("tool_generation", {})
        return {
            "api": openapi_config,
            "mcp_server": {
                "name": server_config.get("name", "API"),
                "description": server_config.get("description", ""),
            },
            "tool_generation": tool_gen_config,
        }

    async def _connect_openapi_server(
        self, server_config: Dict[str, Any], server_index: int = 0
    ) -> Optional[List]:
        """連接 OpenAPI 類型的 MCP Server

        Args:
            server_config: Server 配置
            server_index: 在所有 enabled openapi servers 中的索引
        """
        server_name = server_config.get("name", "OpenAPI Server")
        try:
            logger.debug("   📡 解析 OpenAPI 規格...")
            openapi_config = self._build_openapi_config(server_config)
            parser = OpenAPIParser(openapi_config)
            parsed_spec = parser.parse()

            tools = parsed_spec["tools"]
            self.openapi_tools_summary = parser.generate_tools_summary(tools)
            logger.debug("   📋 發現 %d 個 API 端點", len(tools))

            server_path = str(Path(__file__).parent / "server.py")
            server_params = StdioServerParameters(
                command="python",
                args=[server_path, self.config_path, str(server_index)],
            )

            logger.debug(f"   🚀 啟動 MCP Server 子程序...")
            transport = await self.stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = transport

            session = await self.stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            toolkit = MCPToolkit(session=session)
            await toolkit.initialize()
            tools = toolkit.get_tools()

            api_info = parsed_spec.get("api_info", {})
            # 收集工具詳情
            tools_info = [
                {
                    "name": tool.name,
                    "description": tool.description[:300] if tool.description else "",
                }
                for tool in tools
            ]
            self.connected_servers.append(
                {
                    "name": server_name,
                    "type": "openapi",
                    "description": api_info.get("description", "OpenAPI 服務"),
                    "tool_count": len(tools),
                    "tools": tools_info,
                }
            )

            logger.info("   ✅ %s: 載入 %d 個工具", server_name, len(tools))
            return tools

        except Exception as e:
            logger.error("   ❌ 連接 %s 失敗: %s", server_name, e)
            return None

    async def _connect_external_server(
        self, server_config: Dict[str, Any]
    ) -> Optional[List]:
        """連接外部 MCP Server"""
        server_name = server_config.get("name", "External Server")
        try:
            command = server_config.get("command")
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            expanded_env = {k: self._expand_env_vars(v) for k, v in env.items()}
            full_env = {**os.environ, **expanded_env} if expanded_env else None

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=full_env,
            )

            logger.debug("   🚀 啟動外部 MCP Server: %s %s", command, " ".join(args))
            transport = await self.stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = transport

            session = await self.stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            toolkit = MCPToolkit(session=session)
            await toolkit.initialize()
            tools = toolkit.get_tools()

            # 收集工具詳情
            tools_info = [
                {
                    "name": tool.name,
                    "description": tool.description[:300] if tool.description else "",
                }
                for tool in tools
            ]
            self.connected_servers.append(
                {
                    "name": server_name,
                    "type": "external",
                    "description": server_config.get("description", "外部 MCP 服務"),
                    "tool_count": len(tools),
                    "tools": tools_info,
                }
            )

            logger.info("   ✅ %s: 載入 %d 個工具", server_name, len(tools))
            return tools

        except Exception as e:
            logger.error("   ❌ 連接 %s 失敗: %s", server_name, e)
            return None

    def _generate_system_prompt(self) -> str:
        """生成 System Prompt"""
        servers_info_lines = []
        for server in self.connected_servers:
            servers_info_lines.append(
                f"- {server['name']}: {server.get('description', '已連接')}"
            )
        servers_info = "\n".join(servers_info_lines) if servers_info_lines else "無"

        tools_summary = self.openapi_tools_summary or "（工具將在連接後顯示）"

        prompt_config = self.config.get("system_prompt", {})
        template = prompt_config.get("template", self._get_default_template())

        api_name = self.config.get("mcp_server", {}).get("name", "MCP Assistant")
        api_description = self.config.get("mcp_server", {}).get("description", "")

        return template.format(
            api_name=api_name,
            api_description=api_description,
            tools_summary=tools_summary,
            servers_info=servers_info,
        )

    def _get_default_template(self) -> str:
        """預設的 System Prompt 模板"""
        return """你是一個專業的 AI 助手，可以透過以下工具協助使用者完成任務。

## 🎯 已連接的服務
{servers_info}

## 🛠️ 可用工具
{tools_summary}

## 💬 對話風格
- 使用繁體中文
- 專業但親切的語氣
- 適度使用 emoji 增加可讀性

## ⚠️ 注意事項
1. **資料不存在**：查詢無結果時，清楚說明「查無資料」而非編造
2. **API 錯誤**：若 success=false，顯示 error 訊息並建議用戶稍後再試
3. **確認操作**：執行寫入操作前，確認用戶意圖
"""

    def _get_llm(self):
        """建立 LLM 實例（啟用 streaming）"""
        llm_config = self.config.get("llm", {})
        provider = llm_config.get("provider", "openai")
        model = llm_config.get("model", "gpt-4.1-mini")
        temperature = llm_config.get("temperature", 0)

        if provider == "openai":
            return ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", model),
                temperature=temperature,
                api_key=os.getenv("OPENAI_API_KEY"),
                streaming=True,  # 啟用 streaming
            )
        else:
            raise ValueError(f"不支援的 LLM provider: {provider}")

    async def initialize(self):
        """初始化 MCP 連接"""
        self.stack = AsyncExitStack()
        await self.stack.__aenter__()

        logger.info("=" * 50)
        logger.info("🔌 正在連接 MCP Servers...")
        logger.info("=" * 50)

        # 追蹤 openapi server 的索引
        openapi_server_index = 0

        for server_config in self.mcp_servers:
            server_name = server_config.get("name", "Unknown")
            server_type = server_config.get("type", "unknown")

            logger.info("📡 連接 %s (%s)...", server_name, server_type)

            tools = None
            if server_type == "openapi":
                tools = await self._connect_openapi_server(
                    server_config, openapi_server_index
                )
                openapi_server_index += 1  # 遞增 openapi server 索引
            elif server_type == "external":
                tools = await self._connect_external_server(server_config)

            if tools:
                self.all_tools.extend(tools)

        logger.info("=" * 50)

        if not self.all_tools:
            logger.warning("⚠️  沒有可用的工具")
        else:
            logger.info("📦 總共載入 %d 個工具", len(self.all_tools))
            for tool in self.all_tools:
                logger.debug("   • %s", tool.name)

        # 建立 LLM 和 Agent
        llm_config = self.config.get("llm", {})
        model = os.getenv("OPENAI_MODEL", llm_config.get("model", "gpt-4.1-mini"))
        logger.info("🤖 使用 LLM 模型: %s", model)

        self.llm = self._get_llm()
        self.agent = create_react_agent(self.llm, self.all_tools)
        logger.info("✅ Agent 初始化完成")

    async def cleanup(self):
        """清理資源"""
        logger.info("🧹 清理資源...")
        if self.stack:
            await self.stack.__aexit__(None, None, None)
        logger.info("👋 已關閉所有連接")


async def main():
    """主程式入口"""
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    logger.info("=" * 50)
    logger.info("🚀 MCP Chat Web Server 啟動中...")
    logger.info("=" * 50)

    # 建立 server
    server = MCPWebServer(config_path)

    # 初始化 MCP 連接
    await server.initialize()

    # 取得 app
    app = server.app

    # 設定 port
    port = int(os.getenv("MCP_WEB_PORT", "8080"))

    logger.info("=" * 50)
    logger.info("🌐 網頁伺服器啟動於 http://localhost:%d", port)
    logger.info("   按 Ctrl+C 停止伺服器")
    logger.info("=" * 50)

    # 啟動 uvicorn（使用較低的 log level 避免重複）
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )
    uvicorn_server = uvicorn.Server(config)

    try:
        await uvicorn_server.serve()
    finally:
        await server.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
