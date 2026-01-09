"""
Generic MCP Client
支援多種 MCP Server：OpenAPI/Swagger + 第三方 MCP Server
自動從設定檔生成 System Prompt，並連接到多個 MCP Server
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import AsyncExitStack
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openapi_parser import OpenAPIParser, load_config
from mcp_utils import get_mcp_tools

# 抑制 MCP client 的 JSONRPC 解析警告（第三方 server 可能產生）
logging.getLogger("mcp.client.stdio").setLevel(logging.ERROR)


class GenericMCPClient:
    """通用 MCP Client - 支援多種 MCP Server"""

    def __init__(self, config_path: str = None):
        """
        初始化 Generic MCP Client

        Args:
            config_path: 設定檔路徑，預設為同目錄下的 config.yaml
        """
        # 載入環境變數
        load_dotenv()

        # 載入設定
        self.config = load_config(config_path)
        self.config_path = config_path or str(Path(__file__).parent / "config.yaml")

        # 解析 MCP servers 設定
        self.mcp_servers = self._parse_mcp_servers()

        # 儲存連接資訊（用於生成 system prompt）
        self.connected_servers: List[Dict[str, Any]] = []
        self.openapi_tools_summary: str = ""

    def _parse_mcp_servers(self) -> List[Dict[str, Any]]:
        """解析 MCP servers 設定"""
        servers = []

        # 新格式：mcp_servers 列表
        if "mcp_servers" in self.config:
            for server_config in self.config["mcp_servers"]:
                if server_config.get("enabled", True):
                    servers.append(server_config)

        # 向後兼容：舊格式（單一 OpenAPI server）
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

    def _generate_system_prompt(self) -> str:
        """根據已連接的 servers 生成 System Prompt"""
        # 生成 servers 資訊
        servers_info_lines = []
        for server in self.connected_servers:
            servers_info_lines.append(
                f"- {server['name']}: {server.get('description', '已連接')}"
            )
        servers_info = "\n".join(servers_info_lines) if servers_info_lines else "無"

        # 生成工具摘要
        tools_summary_parts = []

        # OpenAPI 工具摘要
        if self.openapi_tools_summary:
            tools_summary_parts.append(self.openapi_tools_summary)

        # 第三方 server 工具描述
        for server in self.connected_servers:
            if server.get("type") == "external" and server.get("tools_description"):
                tools_summary_parts.append(
                    f"\n### {server['name']}\n{server['tools_description']}"
                )

        tools_summary = (
            "\n".join(tools_summary_parts)
            if tools_summary_parts
            else "（工具將在連接後顯示）"
        )

        # 取得 prompt template
        prompt_config = self.config.get("system_prompt", {})
        template = prompt_config.get("template", self._get_default_template())

        # 取得主要 API 資訊（向後兼容）
        api_name = self.config.get("mcp_server", {}).get("name", "MCP Assistant")
        api_description = self.config.get("mcp_server", {}).get("description", "")

        # 替換變數
        prompt = template.format(
            api_name=api_name,
            api_description=api_description,
            tools_summary=tools_summary,
            servers_info=servers_info,
        )

        return prompt

    def _get_default_template(self) -> str:
        """預設的 System Prompt 模板"""
        return """你是一個專業的 AI 助手，可以透過以下工具協助使用者完成任務。

## 🎯 已連接的服務
{servers_info}

## 🛠️ 可用工具
{tools_summary}

## 📊 資料解讀規範

### 工具回傳格式
所有工具都會回傳 JSON 格式的原始資料，你需要：
1. 解析 JSON 結構
2. 判斷 `success` 欄位是否為 true（若有）
3. 從 `data` 欄位提取實際內容（若有）
4. 以友善的格式呈現給使用者

## 💬 對話風格
- 使用繁體中文
- 專業但親切的語氣
- 適度使用 emoji 增加可讀性

## ⚠️ 注意事項
1. **資料不存在**：查詢無結果時，清楚說明「查無資料」而非編造
2. **API 錯誤**：若 success=false，顯示 error 訊息並建議用戶稍後再試
3. **確認操作**：執行寫入操作前，確認用戶意圖
4. **組合使用**：可以組合多個工具來完成複雜任務

開始為用戶提供服務吧！"""

    def _get_llm(self):
        """根據設定建立 LLM 實例"""
        llm_config = self.config.get("llm", {})
        provider = llm_config.get("provider", "openai")
        model = llm_config.get("model", "gpt-4.1-mini")
        temperature = llm_config.get("temperature", 0)

        if provider == "openai":
            return ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", model),
                temperature=temperature,
                api_key=os.getenv("OPENAI_API_KEY"),
            )
        else:
            raise ValueError(f"不支援的 LLM provider: {provider}")

    def _expand_env_vars(self, value: Any) -> Any:
        """展開環境變數"""
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            return os.getenv(env_var, "")
        return value

    async def _connect_openapi_server(
        self,
        server_config: Dict[str, Any],
        stack: AsyncExitStack,
        server_index: int = 0,
    ) -> Optional[List]:
        """連接 OpenAPI 類型的 MCP Server

        Args:
            server_config: Server 配置
            stack: AsyncExitStack
            server_index: 在所有 enabled openapi servers 中的索引
        """
        server_name = server_config.get("name", "OpenAPI Server")

        try:
            # 建構設定並解析 OpenAPI
            openapi_config = self._build_openapi_config(server_config)
            parser = OpenAPIParser(openapi_config)
            parsed_spec = parser.parse()

            # 生成工具摘要
            tools = parsed_spec["tools"]
            self.openapi_tools_summary = parser.generate_tools_summary(tools)

            # 啟動內建的 server.py
            server_path = str(Path(__file__).parent / "server.py")

            # 建立臨時設定檔路徑（使用原始設定），並傳入 server_index
            server_params = StdioServerParameters(
                command="python",
                args=[server_path, self.config_path, str(server_index)],
            )

            # 建立連線
            transport = await stack.enter_async_context(stdio_client(server_params))
            read, write = transport

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            # 獲取工具（使用官方 MCP SDK）
            tools = await get_mcp_tools(session)

            # 記錄連接資訊
            api_info = parsed_spec.get("api_info", {})
            self.connected_servers.append(
                {
                    "name": server_name,
                    "type": "openapi",
                    "description": api_info.get("description", "OpenAPI 服務"),
                    "tool_count": len(tools),
                }
            )

            return tools

        except Exception as e:
            print(f"   ⚠️  連接失敗: {str(e)}")
            return None

    async def _connect_external_server(
        self, server_config: Dict[str, Any], stack: AsyncExitStack
    ) -> Optional[List]:
        """連接外部 MCP Server"""
        server_name = server_config.get("name", "External Server")

        try:
            command = server_config.get("command")
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            # 展開環境變數
            expanded_env = {k: self._expand_env_vars(v) for k, v in env.items()}

            # 合併當前環境變數
            full_env = {**os.environ, **expanded_env} if expanded_env else None

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=full_env,
            )

            # 建立連線
            transport = await stack.enter_async_context(stdio_client(server_params))
            read, write = transport

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            # 獲取工具（使用官方 MCP SDK）
            tools = await get_mcp_tools(session)

            # 自動從 MCP server 獲取工具描述（如果 config 沒有提供）
            auto_description = server_config.get("description", "")
            auto_tools_description = server_config.get("tools_description", "")

            if not auto_tools_description and tools:
                # 自動生成工具描述
                auto_tools_description = self._generate_tools_description_from_mcp(
                    tools
                )

            if not auto_description and tools:
                # 使用第一個工具的描述作為 server 描述（簡化版）
                auto_description = f"提供 {len(tools)} 個工具"

            # 記錄連接資訊
            self.connected_servers.append(
                {
                    "name": server_name,
                    "type": "external",
                    "description": auto_description or "外部 MCP 服務",
                    "tools_description": auto_tools_description,
                    "tool_count": len(tools),
                }
            )

            return tools

        except Exception as e:
            print(f"   ⚠️  連接失敗: {str(e)}")
            return None

    def _generate_tools_description_from_mcp(self, tools: List) -> str:
        """從 MCP 工具列表自動生成工具描述"""
        lines = []
        for tool in tools:
            tool_name = tool.name
            tool_desc = tool.description or "無描述"
            # 取描述的第一行
            first_line = tool_desc.split("\n")[0][:100]
            lines.append(f"- **{tool_name}**: {first_line}")

            # 嘗試從 tool.args_schema 獲取參數資訊
            if hasattr(tool, "args_schema") and tool.args_schema:
                try:
                    schema = tool.args_schema
                    if hasattr(schema, "model_fields"):
                        # Pydantic v2
                        for field_name, field_info in schema.model_fields.items():
                            required = (
                                "(必填)" if field_info.is_required() else "(可選)"
                            )
                            field_desc = field_info.description or ""
                            lines.append(f"  - {field_name} {required}: {field_desc}")
                    elif hasattr(schema, "schema"):
                        # 嘗試從 JSON schema 獲取
                        json_schema = (
                            schema.schema()
                            if callable(schema.schema)
                            else schema.schema
                        )
                        properties = json_schema.get("properties", {})
                        required_fields = json_schema.get("required", [])
                        for prop_name, prop_info in properties.items():
                            required = (
                                "(必填)" if prop_name in required_fields else "(可選)"
                            )
                            prop_desc = prop_info.get("description", "")
                            lines.append(f"  - {prop_name} {required}: {prop_desc}")
                except Exception:
                    pass  # 忽略解析錯誤

        return "\n".join(lines) if lines else ""

    async def run(self):
        """啟動 Client 互動迴圈"""
        async with AsyncExitStack() as stack:
            all_tools = []

            print("\n🔌 正在連接 MCP Servers...")
            print("-" * 40)

            # 追蹤 openapi server 的索引
            openapi_server_index = 0

            # 連接所有啟用的 MCP servers
            for server_config in self.mcp_servers:
                server_name = server_config.get("name", "Unknown")
                server_type = server_config.get("type", "unknown")

                print(f"   📡 {server_name} ({server_type})...")

                tools = None
                if server_type == "openapi":
                    tools = await self._connect_openapi_server(
                        server_config, stack, openapi_server_index
                    )
                    openapi_server_index += 1  # 遞增 openapi server 索引
                elif server_type == "external":
                    tools = await self._connect_external_server(server_config, stack)
                else:
                    print(f"   ⚠️  不支援的 server 類型: {server_type}")
                    continue

                if tools:
                    all_tools.extend(tools)
                    print(f"   ✅ 已連接，載入 {len(tools)} 個工具")

            print("-" * 40)

            if not all_tools:
                print("\n❌ 沒有可用的工具，請檢查設定檔或確認服務是否正常運行")
                return

            print(f"📦 總共載入 {len(all_tools)} 個工具\n")

            # 生成 System Prompt
            system_prompt = self._generate_system_prompt()

            # 建立 LLM 和 Agent
            llm = self._get_llm()
            agent = create_react_agent(llm, all_tools)

            # 顯示歡迎訊息
            self._print_welcome()

            # 維護對話歷史
            messages = [SystemMessage(content=system_prompt)]

            while True:
                try:
                    user_input = input("\n👤 您：").strip()

                    if not user_input:
                        continue

                    if user_input.lower() in ["quit", "exit", "bye", "結束", "離開"]:
                        print("\n👋 感謝使用，再見！")
                        break

                    if user_input.lower() == "tools":
                        self._print_tools(all_tools)
                        continue

                    if user_input.lower() == "servers":
                        self._print_servers()
                        continue

                    # 加入使用者訊息
                    messages.append(HumanMessage(content=user_input))

                    # 呼叫 agent
                    result = await agent.ainvoke({"messages": messages})

                    # 取得回覆
                    response_messages = result["messages"]
                    response = response_messages[-1].content

                    # 更新對話歷史
                    messages = response_messages

                    print(f"\n🤖 助手：\n{response}")
                    print("-" * 60)

                except KeyboardInterrupt:
                    print("\n\n👋 感謝使用，再見！")
                    break
                except Exception as e:
                    print(f"\n❌ 發生錯誤：{str(e)}\n")

    def _print_welcome(self):
        """顯示歡迎訊息"""
        title = self.config.get("mcp_server", {}).get("name", "MCP Assistant")

        print("=" * 60)
        print(f"🤖 {title}")
        print("=" * 60)

        # 顯示已連接的 servers
        if self.connected_servers:
            print("📡 已連接的服務:")
            for server in self.connected_servers:
                print(f"   • {server['name']} ({server['tool_count']} 個工具)")

        print("-" * 60)
        print("💡 指令說明:")
        print("   • 輸入 'quit' 或 'exit' 結束對話")
        print("   • 輸入 'tools' 查看所有可用工具")
        print("   • 輸入 'servers' 查看已連接的服務")
        print("=" * 60)

    def _print_tools(self, tools: List):
        """顯示所有可用工具"""
        print("\n📋 可用工具列表:")
        print("-" * 40)
        for tool in tools:
            desc = (
                tool.description[:60] + "..."
                if len(tool.description) > 60
                else tool.description
            )
            print(f"   • {tool.name}")
            print(f"     {desc}")
        print("-" * 40)

    def _print_servers(self):
        """顯示已連接的 servers"""
        print("\n📡 已連接的 MCP Servers:")
        print("-" * 40)
        for server in self.connected_servers:
            print(f"   • {server['name']}")
            print(f"     類型: {server['type']}")
            print(f"     工具數: {server['tool_count']}")
            if server.get("description"):
                print(f"     描述: {server['description'][:50]}...")
        print("-" * 40)


async def main():
    """主程式入口"""
    # 支援命令列指定設定檔
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    client = GenericMCPClient(config_path)
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
