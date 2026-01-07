"""
OpenAPI Parser
從 OpenAPI/Swagger 規格自動解析並生成 MCP Tool 定義
"""

import httpx
import json
import re
from typing import Any, Optional
from pathlib import Path
from urllib.parse import urljoin, urlparse


class OpenAPIParser:
    """解析 OpenAPI 規格並生成 MCP Tool 定義"""

    def __init__(self, config: dict, server_index: int = 0):
        self.config = config
        self.server_index = server_index
        self.openapi_spec: dict = {}

        # 支援新格式 mcp_servers 和舊格式 api
        api_config = self._get_api_config()
        self.base_url: str = api_config.get("base_url", "")
        self.timeout: int = api_config.get("timeout", 30)

    def _get_api_config(self) -> dict:
        """取得 API 配置（支援新舊格式）"""
        # 新格式：從 mcp_servers 中找指定索引的 openapi 類型的 server
        if "mcp_servers" in self.config:
            openapi_servers = [
                server for server in self.config["mcp_servers"]
                if server.get("type") == "openapi" and server.get("enabled", True)
            ]
            if openapi_servers and self.server_index < len(openapi_servers):
                return openapi_servers[self.server_index].get("openapi", {})

        # 舊格式：直接使用 api 區塊
        return self.config.get("api", {})

    def load_spec(self) -> dict:
        """載入 OpenAPI 規格（從 URL 或檔案）"""
        api_config = self._get_api_config()

        # 優先從本地檔案載入
        if openapi_file := api_config.get("openapi_file"):
            return self._load_from_file(openapi_file)

        # 從 URL 載入
        if openapi_url := api_config.get("openapi_url"):
            return self._load_from_url(openapi_url)

        raise ValueError("必須在 config.yaml 中設定 openapi_url 或 openapi_file")

    def _load_from_file(self, file_path: str) -> dict:
        """從本地檔案載入 OpenAPI 規格"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"找不到 OpenAPI 規格檔案: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            if path.suffix in [".yaml", ".yml"]:
                import yaml

                return yaml.safe_load(f)
            else:
                return json.load(f)

    def _load_from_url(self, url: str) -> dict:
        """從 URL 載入 OpenAPI 規格

        支援以下 URL 類型：
        1. 直接的 OpenAPI JSON URL (例如 /openapi.json)
        2. Swagger UI 頁面 URL (例如 /docs) - 會自動提取 OpenAPI spec URL
        3. ReDoc 頁面 URL (例如 /redoc) - 會自動提取 OpenAPI spec URL
        """
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")

                # 如果是 JSON，直接返回
                if "application/json" in content_type:
                    return response.json()

                # 如果是 HTML（可能是 /docs 或 /redoc 頁面），嘗試提取 OpenAPI URL
                if "text/html" in content_type:
                    return self._extract_openapi_from_docs_page(
                        client, url, response.text
                    )

                # 嘗試解析為 JSON
                try:
                    return response.json()
                except json.JSONDecodeError:
                    raise ValueError(
                        f"無法解析 URL 內容為 JSON: {url}\n"
                        f"Content-Type: {content_type}\n"
                        f"提示：請確認 URL 是否為 OpenAPI JSON 端點"
                    )

        except httpx.ConnectError:
            raise ConnectionError(f"無法連接到 OpenAPI 規格 URL: {url}")
        except Exception as e:
            if isinstance(e, (ValueError, ConnectionError)):
                raise
            raise RuntimeError(f"載入 OpenAPI 規格失敗: {str(e)}")

    def _extract_openapi_from_docs_page(
        self, client: httpx.Client, docs_url: str, html_content: str
    ) -> dict:
        """從 Swagger UI 或 ReDoc 頁面提取 OpenAPI 規格

        Swagger UI 頁面通常包含類似：
        - url: "/openapi.json"
        - SwaggerUIBundle({ url: "..." })

        ReDoc 頁面通常包含：
        - spec-url="/openapi.json"

        也支援從外部 JS 配置檔案中提取 URL（如氣象局的 od-swagger.js）
        """

        parsed = urlparse(docs_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # 步驟 1: 嘗試從 HTML 內容直接提取 OpenAPI URL
        openapi_url = self._find_openapi_url_in_content(html_content)

        # 步驟 2: 如果找不到，嘗試從外部 JS 檔案中提取
        if not openapi_url:
            openapi_url = self._find_openapi_url_from_scripts(
                client, base, html_content
            )

        # 步驟 3: 如果還是找不到，嘗試常見的 OpenAPI 端點
        if not openapi_url:
            result = self._try_common_openapi_endpoints(client, base)
            if result:
                return result

            raise ValueError(
                f"無法從 {docs_url} 自動提取 OpenAPI 規格 URL。\n"
                f"請嘗試以下方式：\n"
                f"1. 直接提供 openapi.json URL\n"
                f"2. 下載 OpenAPI spec 並使用 openapi_file 設定\n"
                f"3. 在瀏覽器開發者工具的 Network 頁面查找 .json 請求"
            )

        # 將相對路徑轉換為絕對路徑
        full_openapi_url = urljoin(base, openapi_url)
        print(f"從 docs 頁面提取到 OpenAPI URL: {full_openapi_url}")

        # 載入實際的 OpenAPI 規格
        return self._fetch_openapi_spec(client, full_openapi_url)

    def _find_openapi_url_in_content(self, content: str) -> Optional[str]:
        """從內容中尋找 OpenAPI URL"""
        patterns = [
            # Swagger UI patterns
            r'url:\s*["\']([^"\']+)["\']',
            r'"url"\s*:\s*"([^"]+)"',
            r"'url'\s*:\s*'([^']+)'",
            # urls 陣列格式 (如氣象局)
            r'\{\s*url:\s*["\']([^"\']+)["\']',
            # ReDoc
            r'spec-url\s*=\s*["\']([^"\']+)["\']',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                # 過濾掉明顯不是 OpenAPI 的 URL
                if self._is_likely_openapi_url(match):
                    return match

        return None

    def _is_likely_openapi_url(self, url: str) -> bool:
        """判斷 URL 是否可能是 OpenAPI spec"""
        # 排除靜態資源
        excluded_extensions = [
            ".css",
            ".js",
            ".png",
            ".jpg",
            ".ico",
            ".svg",
            ".woff",
            ".ttf",
        ]
        url_lower = url.lower()

        for ext in excluded_extensions:
            if url_lower.endswith(ext):
                return False

        # 排除一些常見的非 API URL
        excluded_patterns = ["fonts.googleapis", "swagger-ui", "favicon"]
        for pattern in excluded_patterns:
            if pattern in url_lower:
                return False

        # 優先匹配的關鍵字
        preferred_keywords = [
            "openapi",
            "swagger",
            "api-docs",
            "apidoc",
            "/api/",
            "/v1/",
            "/v2/",
            "/v3/",
        ]
        for keyword in preferred_keywords:
            if keyword in url_lower:
                return True

        # 如果是相對路徑且看起來像 API 端點
        if url.startswith("/") and not any(
            url.endswith(ext) for ext in excluded_extensions
        ):
            return True

        return False

    def _find_openapi_url_from_scripts(
        self, client: httpx.Client, base_url: str, html_content: str
    ) -> Optional[str]:
        """從 HTML 中引用的外部 JS 檔案尋找 OpenAPI URL"""
        # 找出所有 script src
        script_pattern = r'<script[^>]+src\s*=\s*["\']([^"\']+)["\'][^>]*>'
        script_urls = re.findall(script_pattern, html_content, re.IGNORECASE)

        for script_url in script_urls:
            # 跳過常見的 library
            if any(
                lib in script_url.lower()
                for lib in [
                    "swagger-ui-bundle",
                    "swagger-ui-standalone",
                    "jquery",
                    "bootstrap",
                ]
            ):
                continue

            try:
                full_script_url = urljoin(base_url, script_url)
                resp = client.get(full_script_url)
                if resp.status_code == 200:
                    openapi_url = self._find_openapi_url_in_content(resp.text)
                    if openapi_url:
                        print(f"從外部 JS 檔案 {script_url} 中找到 OpenAPI URL")
                        return openapi_url
            except Exception:
                continue

        return None

    def _try_common_openapi_endpoints(
        self, client: httpx.Client, base_url: str
    ) -> Optional[dict]:
        """嘗試常見的 OpenAPI 端點"""
        from urllib.parse import urljoin

        common_endpoints = [
            "/openapi.json",
            "/swagger.json",
            "/api/openapi.json",
            "/api/swagger.json",
            "/apidoc/v1",
            "/v1/openapi.json",
            "/v2/openapi.json",
            "/v3/openapi.json",
            "/api-docs",
            "/api-docs.json",
            "/docs/openapi.json",
        ]

        for endpoint in common_endpoints:
            try:
                test_url = urljoin(base_url, endpoint)
                resp = client.get(test_url)
                if resp.status_code == 200:
                    spec = self._try_parse_openapi_response(resp)
                    if spec:
                        print(f"在 {test_url} 找到 OpenAPI 規格")
                        return spec
            except Exception:
                continue

        return None

    def _fetch_openapi_spec(self, client: httpx.Client, url: str) -> dict:
        """取得並解析 OpenAPI 規格"""
        response = client.get(url)
        response.raise_for_status()
        return self._try_parse_openapi_response(response)

    def _try_parse_openapi_response(self, response: httpx.Response) -> Optional[dict]:
        """嘗試解析回應為 OpenAPI 規格"""
        content_type = response.headers.get("content-type", "")

        # 嘗試 JSON
        try:
            return response.json()
        except json.JSONDecodeError:
            pass

        # 嘗試 YAML
        try:
            import yaml

            spec = yaml.safe_load(response.text)
            # 驗證是否為 OpenAPI/Swagger 規格
            if isinstance(spec, dict) and ("swagger" in spec or "openapi" in spec):
                return spec
        except Exception:
            pass

        return None

    def parse(self) -> dict:
        """解析 OpenAPI 規格，返回完整的解析結果"""
        self.openapi_spec = self.load_spec()

        # 提取基本資訊
        info = self.openapi_spec.get("info", {})

        # 確定 base_url
        if not self.base_url:
            servers = self.openapi_spec.get("servers", [])
            if servers:
                self.base_url = servers[0].get("url", "")

        return {
            "api_info": {
                "title": info.get("title", "API"),
                "description": info.get("description", ""),
                "version": info.get("version", "1.0.0"),
            },
            "base_url": self.base_url,
            "tools": self._generate_tools(),
            "schemas": self._extract_schemas(),
        }

    def _generate_tools(self) -> list[dict]:
        """從 OpenAPI paths 生成 MCP tool 定義"""
        tools = []
        paths = self.openapi_spec.get("paths", {})
        tool_config = self.config.get("tool_generation", {})

        include_all = tool_config.get("include_all", True)
        include_endpoints = tool_config.get("include_endpoints", [])
        exclude_endpoints = tool_config.get("exclude_endpoints", [])
        snake_case_names = tool_config.get("snake_case_names", True)
        simplified_names = tool_config.get("simplified_names", True)
        tool_prefix = tool_config.get("tool_prefix", "")

        for path, path_item in paths.items():
            for method in ["get", "post", "put", "patch", "delete"]:
                if method not in path_item:
                    continue

                operation = path_item[method]
                operation_id = operation.get("operationId", "")

                # 檢查是否要包含此 endpoint
                if not include_all:
                    if (
                        operation_id not in include_endpoints
                        and path not in include_endpoints
                    ):
                        continue

                # 檢查是否要排除此 endpoint
                if operation_id in exclude_endpoints or path in exclude_endpoints:
                    continue

                # 生成 tool 定義
                tool = self._create_tool_definition(
                    path=path,
                    method=method.upper(),
                    operation=operation,
                    snake_case=snake_case_names,
                    simplified=simplified_names,
                    prefix=tool_prefix,
                )
                tools.append(tool)

        return tools

    def _create_tool_definition(
        self,
        path: str,
        method: str,
        operation: dict,
        snake_case: bool = True,
        simplified: bool = True,
        prefix: str = "",
    ) -> dict:
        """建立單一 tool 定義"""
        # 生成 tool 名稱
        operation_id = operation.get("operationId", "")
        if operation_id:
            tool_name = operation_id
        else:
            # 從 path 生成名稱
            tool_name = f"{method.lower()}_{path.replace('/', '_').replace('-', '_').strip('_')}"

        if snake_case:
            tool_name = self._to_snake_case(tool_name)

        # 簡化名稱（移除 _api_ 和 HTTP method 後綴）
        if simplified:
            tool_name = self._simplify_tool_name(tool_name)

        if prefix:
            tool_name = f"{prefix}{tool_name}"

        # 提取參數
        parameters = self._extract_parameters(operation, path)

        # 提取 request body schema
        request_body = self._extract_request_body(operation)

        # 生成描述
        summary = operation.get("summary", "")
        description = operation.get("description", "")
        full_description = (
            f"{summary}\n\n{description}".strip() if description else summary
        )

        # 生成回傳說明
        response_schema = self._extract_response_schema(operation)

        return {
            "name": tool_name,
            "description": full_description,
            "method": method,
            "path": path,
            "parameters": parameters,
            "request_body": request_body,
            "response_schema": response_schema,
            "tags": operation.get("tags", []),
        }

    def _extract_parameters(self, operation: dict, path: str) -> list[dict]:
        """提取 API 參數定義"""
        params = []

        # 從 path 提取路徑參數
        path_params = re.findall(r"\{(\w+)\}", path)

        for param in operation.get("parameters", []):
            param_def = {
                "name": param.get("name"),
                "in": param.get("in"),  # query, path, header
                "required": param.get("required", False),
                "description": param.get("description", ""),
                "schema": param.get("schema", {}),
            }
            params.append(param_def)

        return params

    def _extract_request_body(self, operation: dict) -> Optional[dict]:
        """提取 request body 定義"""
        request_body = operation.get("requestBody")
        if not request_body:
            return None

        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})

        # 解析 $ref
        if "$ref" in schema:
            schema = self._resolve_ref(schema["$ref"])

        return {
            "required": request_body.get("required", False),
            "description": request_body.get("description", ""),
            "schema": schema,
            "properties": self._extract_properties(schema),
        }

    def _extract_properties(self, schema: dict) -> list[dict]:
        """從 schema 提取屬性定義"""
        properties = []
        required_props = schema.get("required", [])

        for prop_name, prop_schema in schema.get("properties", {}).items():
            # 解析 $ref
            if "$ref" in prop_schema:
                prop_schema = self._resolve_ref(prop_schema["$ref"])

            prop_def = {
                "name": prop_name,
                "type": prop_schema.get("type", "string"),
                "description": prop_schema.get("description", ""),
                "required": prop_name in required_props,
                "default": prop_schema.get("default"),
                "enum": prop_schema.get("enum"),
            }
            properties.append(prop_def)

        return properties

    def _extract_response_schema(self, operation: dict) -> Optional[dict]:
        """提取回應 schema"""
        responses = operation.get("responses", {})

        # 取得成功的回應 (200, 201, etc.)
        for status_code in ["200", "201", "204"]:
            if status_code in responses:
                response = responses[status_code]
                content = response.get("content", {})
                json_content = content.get("application/json", {})
                schema = json_content.get("schema", {})

                if "$ref" in schema:
                    schema = self._resolve_ref(schema["$ref"])

                return schema

        return None

    def _resolve_ref(self, ref: str) -> dict:
        """解析 $ref 引用"""
        # 格式: #/components/schemas/ModelName
        parts = ref.split("/")
        current = self.openapi_spec

        for part in parts[1:]:  # 跳過 #
            current = current.get(part, {})

        return current

    def _extract_schemas(self) -> dict:
        """提取所有 schema 定義"""
        components = self.openapi_spec.get("components", {})
        return components.get("schemas", {})

    def _to_snake_case(self, name: str) -> str:
        """將名稱轉換為 snake_case"""
        # 處理已經是 snake_case 的情況
        if "_" in name and name.islower():
            return name

        # CamelCase -> snake_case
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
        return s2.lower().replace("-", "_").replace("__", "_")

    def _simplify_tool_name(self, name: str) -> str:
        """簡化 tool 名稱，移除冗餘的路徑資訊"""
        # 移除 _api_ 前綴
        name = re.sub(r"_api_", "_", name)

        # 移除結尾的 HTTP method 標記 (如 _get, _post 等)
        name = re.sub(r"_(get|post|put|patch|delete)$", "", name)

        # 處理 FastAPI 自動生成的 operationId 格式
        parts = name.split("_")

        action_words = {
            "get",
            "create",
            "update",
            "delete",
            "approve",
            "reject",
            "list",
            "query",
        }

        # 嘗試找到合理的切分點
        best_name = name

        for i in range(2, len(parts)):
            prefix = "_".join(parts[:i])
            suffix = "_".join(parts[i:])

            # 檢查 suffix 是否是 prefix 的一部分（去掉動作詞後）
            prefix_without_action = prefix
            for action in action_words:
                if prefix.startswith(action + "_"):
                    prefix_without_action = prefix[len(action) + 1 :]
                    break

            # 如果 suffix 以 prefix_without_action 的一部分開頭（處理 detail 等情況）
            # 例如: get_supplier_detail 的 prefix_without_action = supplier_detail
            #       suffix = suppliers_supplier_id
            #       suppliers 是 supplier 的複數形式
            if prefix_without_action:
                # 取 prefix_without_action 的第一個詞
                first_word = prefix_without_action.split("_")[0]
                # 如果 suffix 以這個詞的複數形式或原形開頭
                if suffix.startswith(first_word + "s_") or suffix.startswith(
                    first_word + "_"
                ):
                    best_name = prefix
                    break
                # 或者 suffix 完全以 prefix_without_action 開頭
                if suffix.startswith(prefix_without_action):
                    best_name = prefix
                    break

        name = best_name

        # 清理多餘的下劃線
        name = re.sub(r"_+", "_", name)
        name = name.strip("_")

        return name

    def generate_tools_summary(self, tools: list[dict]) -> str:
        """生成工具摘要（用於 System Prompt）"""
        summary_lines = []

        # 按 tags 分組
        tools_by_tag: dict[str, list[dict]] = {}
        for tool in tools:
            tags = tool.get("tags", ["其他"])
            for tag in tags:
                if tag not in tools_by_tag:
                    tools_by_tag[tag] = []
                tools_by_tag[tag].append(tool)

        for tag, tag_tools in tools_by_tag.items():
            summary_lines.append(f"\n### {tag}")
            for tool in tag_tools:
                method = tool["method"]
                name = tool["name"]
                desc = tool["description"].split("\n")[0]  # 只取第一行
                summary_lines.append(f"- `{name}` ({method}): {desc}")

        return "\n".join(summary_lines)


def load_config(config_path: str = None) -> dict:
    """載入設定檔"""
    import yaml

    if config_path is None:
        # 預設路徑
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


if __name__ == "__main__":
    # 測試用
    config = load_config()
    parser = OpenAPIParser(config)
    result = parser.parse()

    print("=== API Info ===")
    print(json.dumps(result["api_info"], indent=2, ensure_ascii=False))

    print("\n=== Tools ===")
    for tool in result["tools"]:
        print(f"- {tool['name']} ({tool['method']} {tool['path']})")
        print(f"  描述: {tool['description'][:50]}...")
        print(f"  參數: {[p['name'] for p in tool['parameters']]}")
        if tool["request_body"]:
            print(f"  Body: {[p['name'] for p in tool['request_body']['properties']]}")
        print()
