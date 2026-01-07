"""
Generic MCP Service
從 OpenAPI/Swagger 規格自動生成 MCP Tools
"""

from .openapi_parser import OpenAPIParser, load_config
from .server import GenericMCPServer
from .client import GenericMCPClient

__all__ = [
    "OpenAPIParser",
    "load_config",
    "GenericMCPServer",
    "GenericMCPClient",
]

__version__ = "1.0.0"
