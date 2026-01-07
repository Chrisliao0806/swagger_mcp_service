"""
Generic MCP Client
自動從設定檔生成 System Prompt，並連接到 MCP Server
無需任何客製化
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp import MCPToolkit
from langchain.agents import create_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from openapi_parser import OpenAPIParser, load_config


class GenericMCPClient:
    """通用 MCP Client - 從設定檔自動生成 System Prompt"""

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

        # 解析 OpenAPI（用於生成 System Prompt）
        self.parser = OpenAPIParser(self.config)
        self.parsed_spec = self.parser.parse()

        # 生成 System Prompt
        self.system_prompt = self._generate_system_prompt()

    def _generate_system_prompt(self) -> str:
        """根據設定檔和 OpenAPI 規格生成 System Prompt"""
        api_info = self.parsed_spec["api_info"]
        tools = self.parsed_spec["tools"]

        # 生成工具摘要
        tools_summary = self.parser.generate_tools_summary(tools)

        # 取得 prompt template
        prompt_config = self.config.get("system_prompt", {})
        template = prompt_config.get("template", self._get_default_template())

        # 替換變數
        prompt = template.format(
            api_name=api_info.get("title", "API"),
            api_description=api_info.get("description", ""),
            tools_summary=tools_summary,
        )

        return prompt

    def _get_default_template(self) -> str:
        """預設的 System Prompt 模板"""
        return """你是一個專業的 AI 助手，可以透過以下 API 工具協助使用者完成任務。

## 🎯 系統資訊
- API 名稱：{api_name}
- 描述：{api_description}

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

    async def run(self):
        """啟動 Client 互動迴圈"""
        # 取得 server.py 的路徑
        server_path = str(Path(__file__).parent / "server.py")

        # MCP Server 連線配置
        server_params = StdioServerParameters(
            command="python",
            args=[server_path, self.config_path],
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # 初始化 session
                await session.initialize()

                # 建立 MCPToolkit
                toolkit = MCPToolkit(session=session)
                await toolkit.initialize()
                tools = toolkit.get_tools()

                # 建立 LLM
                llm = self._get_llm()

                # 建立 Agent
                agent = create_agent(llm, tools, system_prompt=self.system_prompt)

                # 顯示歡迎訊息
                api_info = self.parsed_spec["api_info"]
                self._print_welcome(api_info)

                # 維護對話歷史
                messages = []

                while True:
                    try:
                        user_input = input("\n👤 您：").strip()

                        if not user_input:
                            continue

                        if user_input.lower() in [
                            "quit",
                            "exit",
                            "bye",
                            "結束",
                            "離開",
                        ]:
                            print("\n👋 感謝使用，再見！")
                            break

                        # 加入使用者訊息
                        messages.append({"role": "user", "content": user_input})

                        # 呼叫 agent
                        result = await agent.ainvoke({"messages": messages})

                        # 取得回覆
                        response = result["messages"][-1].content

                        # 加入助手回覆到歷史
                        messages.append({"role": "assistant", "content": response})

                        print(f"\n🤖 助手：\n{response}")
                        print("-" * 60)

                    except KeyboardInterrupt:
                        print("\n\n👋 感謝使用，再見！")
                        break
                    except Exception as e:
                        print(f"\n❌ 發生錯誤：{str(e)}\n")

    def _print_welcome(self, api_info: dict):
        """顯示歡迎訊息"""
        title = api_info.get("title", "API Assistant")
        description = api_info.get("description", "")

        print("=" * 60)
        print(f"🤖 {title}")
        print("=" * 60)

        if description:
            # 只取描述的前幾行
            desc_lines = description.strip().split("\n")[:3]
            for line in desc_lines:
                print(f"   {line.strip()}")

        print("-" * 60)
        print("💡 輸入 'quit' 或 'exit' 結束對話")
        print("=" * 60)


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
