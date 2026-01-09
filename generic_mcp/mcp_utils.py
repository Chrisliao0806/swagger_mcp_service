"""
MCP 工具轉換工具
將 MCP 工具轉換為 LangChain StructuredTool 格式
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
import concurrent.futures

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from pydantic import create_model, Field


def _json_schema_to_pydantic_type(schema: Dict[str, Any]) -> Any:
    """將 JSON Schema 類型轉換為 Python 類型"""
    json_type = schema.get("type", "string")

    if json_type == "string":
        return str
    elif json_type == "integer":
        return int
    elif json_type == "number":
        return float
    elif json_type == "boolean":
        return bool
    elif json_type == "array":
        return list
    elif json_type == "object":
        return dict
    else:
        return str


def _create_mcp_tool(session: ClientSession, tool_info: Any) -> StructuredTool:
    """
    將 MCP 工具轉換為 LangChain StructuredTool

    Args:
        session: MCP ClientSession
        tool_info: MCP 工具資訊

    Returns:
        LangChain StructuredTool
    """
    tool_name = tool_info.name
    tool_description = tool_info.description or "無描述"
    input_schema = tool_info.inputSchema or {}

    # 從 inputSchema 建立 Pydantic model
    properties = input_schema.get("properties", {})
    required_fields = input_schema.get("required", [])

    # 建立欄位定義
    field_definitions = {}
    for prop_name, prop_info in properties.items():
        prop_type = _json_schema_to_pydantic_type(prop_info)
        prop_desc = prop_info.get("description", "")
        is_required = prop_name in required_fields

        if is_required:
            field_definitions[prop_name] = (prop_type, Field(description=prop_desc))
        else:
            field_definitions[prop_name] = (
                Optional[prop_type],
                Field(default=None, description=prop_desc),
            )

    # 如果沒有參數，建立一個空的 model
    if not field_definitions:
        args_model = None
    else:
        args_model = create_model(f"{tool_name}_Args", **field_definitions)

    async def call_tool(**kwargs) -> str:
        """呼叫 MCP 工具"""
        try:
            result = await session.call_tool(tool_name, arguments=kwargs)

            # 處理回傳結果
            if hasattr(result, "content") and result.content:
                # 提取文字內容
                contents = []
                for content in result.content:
                    if hasattr(content, "text"):
                        contents.append(content.text)
                    elif hasattr(content, "data"):
                        contents.append(str(content.data))
                    else:
                        contents.append(str(content))
                return "\n".join(contents)
            elif hasattr(result, "isError") and result.isError:
                return f"錯誤: {result}"
            else:
                return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return f"工具呼叫失敗: {str(e)}"

    # 建立同步包裝函數（LangChain 需要）
    def sync_call_tool(**kwargs) -> str:
        """同步呼叫 MCP 工具（透過 asyncio）"""
        loop = asyncio.get_event_loop()
        if loop.is_running():

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, call_tool(**kwargs))
                return future.result()
        else:
            return asyncio.run(call_tool(**kwargs))

    # 建立 StructuredTool
    if args_model:
        return StructuredTool(
            name=tool_name,
            description=tool_description,
            func=sync_call_tool,
            coroutine=call_tool,
            args_schema=args_model,
        )
    else:
        return StructuredTool.from_function(
            name=tool_name,
            description=tool_description,
            func=lambda: sync_call_tool(),
            coroutine=lambda: call_tool(),
        )


async def get_mcp_tools(session: ClientSession) -> List[StructuredTool]:
    """
    從 MCP session 獲取所有工具並轉換為 LangChain 格式

    Args:
        session: MCP ClientSession

    Returns:
        LangChain StructuredTool 列表
    """
    # 列出所有 MCP 工具
    tools_result = await session.list_tools()
    mcp_tools = tools_result.tools if hasattr(tools_result, "tools") else []

    # 轉換為 LangChain 工具
    langchain_tools = []
    for tool_info in mcp_tools:
        lc_tool = _create_mcp_tool(session, tool_info)
        langchain_tools.append(lc_tool)

    return langchain_tools
