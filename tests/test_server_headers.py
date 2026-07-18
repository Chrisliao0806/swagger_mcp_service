from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

fastmcp_module = types.ModuleType("mcp.server.fastmcp")
fastmcp_module.FastMCP = object
server_package = types.ModuleType("mcp.server")
mcp_package = types.ModuleType("mcp")
sys.modules.setdefault("mcp", mcp_package)
sys.modules.setdefault("mcp.server", server_package)
sys.modules.setdefault("mcp.server.fastmcp", fastmcp_module)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generic_mcp"))

from server import GenericMCPServer


class ResponseStub:
    status_code = 200

    @staticmethod
    def raise_for_status():
        return None

    @staticmethod
    def json():
        return {"success": True}


class ClientStub:
    def __init__(self):
        self.headers = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, _url, *, params, headers):
        self.headers = headers
        return ResponseStub()


class ServerHeaderTests(unittest.TestCase):
    def test_forwards_configured_headers_to_api_request(self):
        server = object.__new__(GenericMCPServer)
        server.base_url = "https://api.example"
        server.timeout = 30
        server.headers = {"Authorization": "configured-token"}
        client = ClientStub()

        with patch("server.httpx.Client", return_value=client):
            result = server._call_api("/items")

        self.assertEqual(result, {"success": True})
        self.assertEqual(client.headers, {"Authorization": "configured-token"})


if __name__ == "__main__":
    unittest.main()
