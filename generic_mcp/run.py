#!/usr/bin/env python3
"""
Generic MCP Service 啟動腳本
一鍵啟動 MCP Client（會自動啟動 Server）

使用方式：
    python run.py                    # 使用預設 config.yaml
    python run.py --config my.yaml   # 使用自訂設定檔
    python run.py --server-only      # 只啟動 Server（用於除錯）
    python run.py --validate         # 驗證設定檔和 OpenAPI 規格
    python run.py --list-tools       # 列出所有可用工具
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 將當前目錄加入 path
sys.path.insert(0, str(Path(__file__).parent))


def validate_config(config_path: str = None):
    """驗證設定檔和 OpenAPI 規格"""
    from openapi_parser import OpenAPIParser, load_config

    print("🔍 驗證設定檔...")

    try:
        config = load_config(config_path)
        print("   ✅ 設定檔載入成功")
    except Exception as e:
        print(f"   ❌ 設定檔載入失敗: {e}")
        return False

    print("\n🔍 驗證 OpenAPI 規格...")

    try:
        parser = OpenAPIParser(config)
        result = parser.parse()
        print("   ✅ OpenAPI 規格載入成功")
        print(f"   📋 API 名稱: {result['api_info']['title']}")
        print(f"   🔗 Base URL: {result['base_url']}")
        print(f"   🛠️  工具數量: {len(result['tools'])}")
    except ConnectionError as e:
        print(f"   ❌ 無法連接到 OpenAPI URL: {e}")
        print("   💡 請確認 API Server 已啟動")
        return False
    except Exception as e:
        print(f"   ❌ OpenAPI 規格解析失敗: {e}")
        return False

    print("\n✅ 驗證完成，設定正確！")
    return True


def list_tools(config_path: str = None):
    """列出所有可用工具"""
    from openapi_parser import OpenAPIParser, load_config

    config = load_config(config_path)
    parser = OpenAPIParser(config)
    result = parser.parse()

    print("=" * 60)
    print(f"🛠️  {result['api_info']['title']} - 可用工具列表")
    print("=" * 60)

    # 按 tags 分組顯示
    tools_by_tag = {}
    for tool in result["tools"]:
        tags = tool.get("tags", ["其他"])
        for tag in tags:
            if tag not in tools_by_tag:
                tools_by_tag[tag] = []
            tools_by_tag[tag].append(tool)

    for tag, tools in tools_by_tag.items():
        print(f"\n📁 {tag}")
        print("-" * 40)
        for tool in tools:
            print(f"  • {tool['name']}")
            print(f"    {tool['method']} {tool['path']}")
            desc = tool["description"].split("\n")[0][:60]
            print(f"    {desc}...")

            # 顯示參數
            params = tool.get("parameters", [])
            body = tool.get("request_body")
            all_params = []

            for p in params:
                req = "必填" if p.get("required") else "選填"
                all_params.append(f"{p['name']}({req})")

            if body:
                for p in body.get("properties", []):
                    req = "必填" if p.get("required") else "選填"
                    all_params.append(f"{p['name']}({req})")

            if all_params:
                print(f"    參數: {', '.join(all_params)}")
            print()


def run_server_only(config_path: str = None):
    """只啟動 Server"""
    from server import GenericMCPServer

    print("🚀 啟動 MCP Server...")
    server = GenericMCPServer(config_path)
    server.run()


async def run_client(config_path: str = None):
    """啟動 Client（會自動啟動 Server）"""
    from client import GenericMCPClient

    client = GenericMCPClient(config_path)
    await client.run()


def main():
    parser = argparse.ArgumentParser(
        description="Generic MCP Service - 從 OpenAPI 規格自動生成 MCP 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python run.py                        啟動互動式 Client
  python run.py --config my.yaml       使用自訂設定檔
  python run.py --validate             驗證設定
  python run.py --list-tools           列出所有工具
  python run.py --server-only          只啟動 Server
        """,
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="設定檔路徑（預設為 config.yaml）",
    )

    parser.add_argument(
        "--validate",
        "-v",
        action="store_true",
        help="驗證設定檔和 OpenAPI 規格",
    )

    parser.add_argument(
        "--list-tools",
        "-l",
        action="store_true",
        help="列出所有可用工具",
    )

    parser.add_argument(
        "--server-only",
        "-s",
        action="store_true",
        help="只啟動 MCP Server（用於除錯）",
    )

    args = parser.parse_args()

    # 設定檔路徑
    config_path = args.config
    if config_path:
        config_path = str(Path(config_path).resolve())

    try:
        if args.validate:
            validate_config(config_path)
        elif args.list_tools:
            list_tools(config_path)
        elif args.server_only:
            run_server_only(config_path)
        else:
            asyncio.run(run_client(config_path))
    except KeyboardInterrupt:
        print("\n\n👋 再見！")
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
