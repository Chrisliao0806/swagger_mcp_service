import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generic_mcp"))

from openapi_parser import (
    OpenAPIParser,
    expand_header_environment_variables,
)


class OpenAPIConfigurationTests(unittest.TestCase):
    def test_uses_tool_generation_from_selected_server(self):
        config = {
            "mcp_servers": [
                {
                    "type": "openapi",
                    "enabled": True,
                    "openapi": {"base_url": "https://first.example"},
                    "tool_generation": {
                        "include_all": False,
                        "include_endpoints": ["firstOperation"],
                    },
                },
                {
                    "type": "openapi",
                    "enabled": True,
                    "openapi": {"base_url": "https://second.example"},
                    "tool_generation": {
                        "include_all": False,
                        "include_endpoints": ["secondOperation"],
                    },
                },
            ]
        }
        parser = OpenAPIParser(config, server_index=1)
        parser.openapi_spec = {
            "paths": {
                "/first": {"get": {"operationId": "firstOperation"}},
                "/second": {"get": {"operationId": "secondOperation"}},
            }
        }

        tools = parser._generate_tools()

        self.assertEqual([tool["path"] for tool in tools], ["/second"])

    @patch.dict(os.environ, {"SERVICE_TOKEN": "configured-token"})
    def test_expands_header_environment_variable(self):
        headers = expand_header_environment_variables(
            {"Authorization": "${SERVICE_TOKEN}", "Accept": "application/json"}
        )

        self.assertEqual(
            headers,
            {
                "Authorization": "configured-token",
                "Accept": "application/json",
            },
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_rejects_missing_header_environment_variable(self):
        with self.assertRaisesRegex(ValueError, "SERVICE_TOKEN"):
            expand_header_environment_variables(
                {"Authorization": "${SERVICE_TOKEN}"}
            )


if __name__ == "__main__":
    unittest.main()
