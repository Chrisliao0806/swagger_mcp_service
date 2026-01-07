"""
Generic MCP Server
自動從 OpenAPI 規格生成 MCP Tools，無需任何客製化

================================================================================
MCP Tool 程式碼結構說明
================================================================================

一個標準的 MCP Tool 定義如下：

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("My Server")

    @mcp.tool()
    def my_tool_name(
        required_param: str,           # 必填參數
        optional_param: str = None     # 選填參數
    ) -> str:
        \"\"\"
        工具的描述說明 (這會顯示給 LLM 看，讓它知道何時該使用這個工具)

        Args:
            required_param: 必填參數的說明
            optional_param: 選填參數的說明
        \"\"\"
        # 工具的實作邏輯
        result = do_something(required_param, optional_param)
        return json.dumps(result)  # 回傳字串格式

--------------------------------------------------------------------------------
本程式的運作原理：
--------------------------------------------------------------------------------

1. 從 OpenAPI 規格 (openapi.json) 解析出所有 API 端點
2. 每個 API 端點會被轉換成一個 MCP Tool，結構對應如下：

   OpenAPI 端點                    →  MCP Tool
   ─────────────────────────────────────────────────
   operationId / 路徑+方法         →  tool 名稱 (函數名)
   summary / description          →  tool 描述 (docstring)
   path parameters                →  必填參數 (in="path")
   query parameters               →  查詢參數 (in="query")
   request body properties        →  請求體參數

3. 動態生成的工具函數會：
   - 將參數分類 (path / query / body)
   - 組合成 HTTP 請求
   - 呼叫實際的 API
   - 回傳 JSON 格式的結果

範例：假設 OpenAPI 有這個端點

    POST /purchase-orders
    summary: "建立採購單"
    requestBody:
      properties:
        supplier_name: { type: string, description: "供應商名稱" }
        items: { type: array, description: "採購項目" }

會自動生成類似這樣的 MCP Tool：

    @mcp.tool()
    def create_purchase_order(
        supplier_name: str,
        items: list
    ) -> str:
        \"\"\"建立採購單

        Args:
            supplier_name: 供應商名稱
            items: 採購項目
        \"\"\"
        # 自動生成的 API 呼叫邏輯...

================================================================================
"""

import sys
import json
import logging
import re
import httpx
from typing import Any, Optional, Callable
from pathlib import Path
from mcp.server.fastmcp import FastMCP

from openapi_parser import OpenAPIParser, load_config

# 設定 logger
logger = logging.getLogger(__name__)


class GenericMCPServer:
    """通用 MCP Server - 從 OpenAPI 規格自動生成工具"""

    def __init__(self, config_path: str = None, server_index: int = 0):
        """
        初始化 Generic MCP Server

        Args:
            config_path: 設定檔路徑，預設為同目錄下的 config.yaml
            server_index: 要使用的 openapi server 索引（當有多個 openapi server 時）
        """
        # 載入設定
        self.config = load_config(config_path)
        self.server_index = server_index
        logger.info("設定檔載入完成: %s", config_path or "預設路徑")
        logger.info("使用 OpenAPI Server 索引: %d", server_index)

        # 解析 OpenAPI
        self.parser = OpenAPIParser(self.config, server_index)
        self.parsed_spec = self.parser.parse()
        logger.info("OpenAPI 規格解析完成")

        # 設定基本資訊
        self.api_info = self.parsed_spec["api_info"]
        self.base_url = self.parsed_spec["base_url"]
        self.tools_def = self.parsed_spec["tools"]
        self.timeout = self._get_timeout()

        logger.info(
            "API 資訊: %s (版本: %s)",
            self.api_info["title"],
            self.api_info.get("version", "未知"),
        )
        logger.info("Base URL: %s", self.base_url)
        logger.info("Timeout: %s 秒", self.timeout)

        # 建立 MCP Server
        server_name = self._get_server_name()

        self.mcp = FastMCP(server_name)
        logger.info("MCP Server 已建立: %s", server_name)

        # 動態註冊所有工具
        self._register_tools()

    def _get_api_config(self) -> dict:
        """取得 API 配置（支援新舊格式）"""
        # 新格式：從 mcp_servers 中找指定索引的 openapi 類型的 server
        if "mcp_servers" in self.config:
            openapi_servers = [
                server
                for server in self.config["mcp_servers"]
                if server.get("type") == "openapi" and server.get("enabled", True)
            ]
            if openapi_servers and self.server_index < len(openapi_servers):
                return openapi_servers[self.server_index].get("openapi", {})

        # 舊格式：直接使用 api 區塊
        return self.config.get("api", {})

    def _get_timeout(self) -> int:
        """取得 timeout 設定"""
        return self._get_api_config().get("timeout", 30)

    def _get_server_name(self) -> str:
        """取得 server 名稱"""
        # 新格式：從 mcp_servers 取得指定索引的 server 名稱
        if "mcp_servers" in self.config:
            openapi_servers = [
                server
                for server in self.config["mcp_servers"]
                if server.get("type") == "openapi" and server.get("enabled", True)
            ]
            if openapi_servers and self.server_index < len(openapi_servers):
                return openapi_servers[self.server_index].get(
                    "name", self.api_info["title"]
                )

        # 舊格式：從 mcp_server 取得
        return self.config.get("mcp_server", {}).get("name", self.api_info["title"])

    def _call_api(
        self,
        path: str,
        method: str = "GET",
        path_params: dict = None,
        query_params: dict = None,
        json_data: dict = None,
    ) -> dict:
        """
        通用 API 呼叫函數
        """
        # 替換路徑參數
        if path_params:
            for key, value in path_params.items():
                path = path.replace(f"{{{key}}}", str(value))

        url = f"{self.base_url}{path}"

        # 過濾 None 值
        if query_params:
            query_params = {k: v for k, v in query_params.items() if v is not None}
        if json_data:
            json_data = {k: v for k, v in json_data.items() if v is not None}

        logger.debug("API 呼叫: %s %s", method.upper(), url)
        if query_params:
            logger.debug("Query 參數: %s", query_params)
        if json_data:
            logger.debug("Body 資料: %s", json_data)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                if method.upper() == "GET":
                    response = client.get(url, params=query_params)
                elif method.upper() == "POST":
                    response = client.post(url, params=query_params, json=json_data)
                elif method.upper() == "PUT":
                    response = client.put(url, params=query_params, json=json_data)
                elif method.upper() == "PATCH":
                    response = client.patch(url, params=query_params, json=json_data)
                elif method.upper() == "DELETE":
                    response = client.delete(url, params=query_params)
                else:
                    logger.warning("不支援的 HTTP 方法: %s", method)
                    return {
                        "success": False,
                        "error": "不支援的 HTTP 方法: %s" % method,
                    }

                response.raise_for_status()
                logger.debug("API 回應狀態碼: %s", response.status_code)

                # 嘗試解析 JSON，若失敗則返回原始文字
                try:
                    return response.json()
                except json.JSONDecodeError:
                    logger.debug("回應非 JSON 格式，返回原始文字")
                    return {"success": True, "data": response.text}

        except httpx.ConnectError:
            logger.error("無法連接到 API Server: %s", self.base_url)
            return {
                "success": False,
                "error": "無法連接到 API Server (%s)，請確認服務已啟動" % self.base_url,
            }
        except httpx.HTTPStatusError as e:
            logger.error("API 請求失敗，狀態碼: %s", e.response.status_code)
            try:
                error_detail = e.response.json()
            except:
                error_detail = e.response.text
            return {
                "success": False,
                "error": "API 請求失敗 (HTTP %s)" % e.response.status_code,
                "detail": error_detail,
            }
        except Exception as e:
            logger.exception("API 呼叫發生未預期錯誤")
            return {"success": False, "error": "API 呼叫錯誤: %s" % str(e)}

    def _register_tools(self):
        """動態註冊所有從 OpenAPI 解析出的工具"""
        logger.info("開始註冊工具，共 %d 個", len(self.tools_def))
        for tool_def in self.tools_def:
            self._register_single_tool(tool_def)
        logger.info("所有工具註冊完成")

    def _register_single_tool(self, tool_def: dict):
        """註冊單一工具"""
        tool_name = tool_def["name"]
        method = tool_def["method"]
        path = tool_def["path"]
        description = tool_def["description"]
        parameters = tool_def["parameters"]
        request_body = tool_def.get("request_body")

        # 建立完整的 docstring
        docstring = self._build_docstring(tool_def)

        # 建立動態函數
        def make_tool_func(path, method, parameters, request_body):
            def tool_func(**kwargs) -> str:
                """動態生成的 API 呼叫函數"""
                path_params = {}
                query_params = {}
                body_data = {}

                # 分類參數
                for param in parameters:
                    param_name = param["name"]
                    if param_name in kwargs:
                        value = kwargs[param_name]
                        if param["in"] == "path":
                            path_params[param_name] = value
                        elif param["in"] == "query":
                            query_params[param_name] = value
                        elif param["in"] == "header":
                            # TODO: 支援 header 參數
                            pass

                # 處理 request body
                if request_body:
                    for prop in request_body.get("properties", []):
                        prop_name = prop["name"]
                        if prop_name in kwargs:
                            body_data[prop_name] = kwargs[prop_name]

                # 呼叫 API
                result = self._call_api(
                    path=path,
                    method=method,
                    path_params=path_params if path_params else None,
                    query_params=query_params if query_params else None,
                    json_data=body_data if body_data else None,
                )

                return json.dumps(result, ensure_ascii=False, indent=2)

            return tool_func

        # 建立函數
        func = make_tool_func(path, method, parameters, request_body)
        func.__name__ = tool_name
        func.__doc__ = docstring

        # 使用 @mcp.tool() 裝飾器註冊
        # 由於需要動態綁定 self，這裡採用另一種方式
        self._register_with_mcp(tool_name, func, tool_def)

    def _register_with_mcp(self, name: str, func: Callable, tool_def: dict):
        """使用 FastMCP 註冊工具"""
        # 建立參數型別提示
        parameters = tool_def.get("parameters", [])
        request_body = tool_def.get("request_body")

        # 收集所有參數
        all_params = []

        for param in parameters:
            all_params.append(
                {
                    "name": param["name"],
                    "type": self._get_python_type(param.get("schema", {})),
                    "required": param.get("required", False),
                    "description": param.get("description", ""),
                    "default": param.get("schema", {}).get("default"),
                }
            )

        if request_body:
            for prop in request_body.get("properties", []):
                all_params.append(
                    {
                        "name": prop["name"],
                        "type": self._get_python_type(
                            {"type": prop.get("type", "string")}
                        ),
                        "required": prop.get("required", False),
                        "description": prop.get("description", ""),
                        "default": prop.get("default"),
                    }
                )

        # 建立帶有正確參數定義的函數
        wrapped_func = self._create_typed_function(
            name, func, all_params, tool_def["description"]
        )

        # 註冊到 MCP
        self.mcp.tool()(wrapped_func)
        logger.debug("工具已註冊: %s (參數數量: %d)", name, len(all_params))

    def _create_typed_function(
        self, name: str, func: Callable, params: list, description: str
    ) -> Callable:
        """建立具有型別提示的函數"""
        # 排序參數：必填參數在前，選填參數在後
        sorted_params = sorted(params, key=lambda p: (not p["required"], p["name"]))

        # 動態建立函數參數
        param_strs = []
        for param in sorted_params:
            ptype = param["type"]
            pname = param["name"]

            if param["required"]:
                param_strs.append(f"{pname}: {ptype}")
            else:
                default = param.get("default")
                if default is None:
                    param_strs.append(f"{pname}: Optional[{ptype}] = None")
                else:
                    if isinstance(default, str):
                        param_strs.append(f'{pname}: {ptype} = "{default}"')
                    else:
                        param_strs.append(f"{pname}: {ptype} = {default}")

        # 建立函數程式碼
        params_str = ", ".join(param_strs) if param_strs else ""

        # 建立 docstring（使用排序後的參數）
        doc_lines = [description, "", "Args:"]
        for param in sorted_params:
            doc_lines.append(f"    {param['name']}: {param['description']}")
        docstring = "\n".join(doc_lines)

        # 使用 exec 動態建立函數
        func_code = f'''
def {name}({params_str}) -> str:
    """{docstring}"""
    kwargs = {{k: v for k, v in locals().items() if v is not None}}
    return func(**kwargs)
'''

        local_vars = {"func": func, "Optional": Optional}
        exec(func_code, local_vars)

        return local_vars[name]

    def _get_python_type(self, schema: dict) -> str:
        """將 OpenAPI 型別轉換為 Python 型別字串"""
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict",
        }

        openapi_type = schema.get("type", "string")
        return type_map.get(openapi_type, "str")

    def _build_docstring(self, tool_def: dict) -> str:
        """建立完整的 docstring"""
        lines = [tool_def["description"], ""]

        # 參數說明
        params = tool_def.get("parameters", [])
        request_body = tool_def.get("request_body")

        if params or request_body:
            lines.append("Args:")

            for param in params:
                required = " (必填)" if param.get("required") else ""
                lines.append(
                    f"    {param['name']}{required}: {param.get('description', '')}"
                )

            if request_body:
                for prop in request_body.get("properties", []):
                    required = " (必填)" if prop.get("required") else ""
                    lines.append(
                        f"    {prop['name']}{required}: {prop.get('description', '')}"
                    )

        return "\n".join(lines)

    def run(self):
        """啟動 MCP Server"""
        debug = self.config.get("advanced", {}).get("debug", False)
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.debug("已載入 %d 個工具", len(self.tools_def))
            for tool in self.tools_def:
                logger.debug(
                    "  - %s (%s %s)", tool["name"], tool["method"], tool["path"]
                )
        else:
            logging.basicConfig(level=logging.INFO)

        logger.info("MCP Server 啟動中...")
        logger.info("已註冊的工具列表:")
        for tool in self.tools_def:
            logger.info("  ✓ %s [%s %s]", tool["name"], tool["method"], tool["path"])

        self.mcp.run()


def main():
    # 支援命令列指定設定檔和 server index
    config_path = None
    server_index = 0

    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            server_index = int(sys.argv[2])
        except ValueError:
            logger.warning("無效的 server_index: %s，使用預設值 0", sys.argv[2])

    server = GenericMCPServer(config_path, server_index)
    server.run()


if __name__ == "__main__":
    main()
