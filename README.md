# Swagger MCP Service

<p align="center">
  <b>🔄 Automatically Transform Any OpenAPI/Swagger API into MCP (Model Context Protocol) Tools</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/MCP-1.0+-orange.svg" alt="MCP Version">
</p>

---

## 🌟 Overview

**Swagger MCP Service** is a powerful, zero-code solution that automatically converts any OpenAPI/Swagger specification into MCP (Model Context Protocol) tools. This enables Large Language Models (LLMs) to seamlessly interact with your existing REST APIs without writing any custom integration code.

### Key Features

- 🚀 **Zero-Code Integration** - Just provide an OpenAPI spec URL, and the system handles everything
- 🔄 **Dynamic Tool Generation** - Automatically parses API endpoints and generates MCP tools
- 🤖 **LLM-Ready** - Works with OpenAI GPT models out of the box via LangChain
- 📋 **Smart Parsing** - Supports Swagger UI, ReDoc, and direct OpenAPI JSON endpoints
- ⚙️ **Highly Configurable** - Customize tool names, filters, system prompts, and more via YAML
- 🔌 **Multi-Server Support** - Connect to multiple MCP servers simultaneously (OpenAPI + third-party)
- 🆕 **Auto Tool Discovery** - Automatically fetches tool descriptions from third-party MCP servers
- 🧩 **Extensible Architecture** - Clean separation between server, client, and parser components
- 🌐 **Beautiful Web Interface** - Modern chat UI with real-time streaming responses
- 📊 **Comprehensive Logging** - Colored console logs with performance metrics

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Swagger MCP Service                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ┌─────────────┐        ┌────────────────┐                              │
│   │   Browser   │───────▶│  Web Interface │  (SSE Streaming)             │
│   │   /User     │◀───────│ (web_server.py)│                              │
│   └─────────────┘        └────────┬───────┘                              │
│                                   │                                       │
│   ┌─────────────┐                 │                                       │
│   │     CLI     │────┐            │  FastAPI + LangGraph                  │
│   │  (run.py)   │    │            │                                       │
│   └─────────────┘    │            ▼                                       │
│                      │    ┌──────────────┐     ┌──────────────────────┐  │
│                      └───▶│  MCP Client  │────▶│     LLM (GPT-4)      │  │
│                           │ (client.py)  │◀────│    via LangChain     │  │
│                           └──────┬───────┘     └──────────────────────┘  │
│                                  │                                        │
│                                  │ stdio (multiple connections)           │
│                       ┌──────────┴──────────┐                             │
│                       ▼                     ▼                             │
│               ┌──────────────┐     ┌──────────────────┐                  │
│               │  MCP Server  │     │  3rd Party MCP   │                  │
│               │ (server.py)  │     │ (mcp-server-*)   │                  │
│               └──────┬───────┘     └──────────────────┘                  │
│                      │                                                    │
│                      │ Dynamic Tool Registration                          │
│                      ▼                                                    │
│            ┌─────────────────────┐                                        │
│            │   OpenAPI Parser    │                                        │
│            │ (openapi_parser.py) │                                        │
│            └─────────┬───────────┘                                        │
│                      │                                                    │
│                      │ Parse & Transform                                  │
│                      ▼                                                    │
│           ┌──────────────────────┐                                        │
│           │   OpenAPI/Swagger    │                                        │
│           │    Specification     │                                        │
│           └──────────┬───────────┘                                        │
│                      │                                                    │
└──────────────────────┼────────────────────────────────────────────────────┘
                       │ HTTP Requests
                       ▼
               ┌──────────────┐
               │  Target API  │
               │   Server     │
               └──────────────┘
```

### Component Overview

| Component | File | Description |
|-----------|------|-------------|
| **Run Script** | `run.py` | Entry point with CLI for validation, listing tools, and running the service |
| **MCP Server** | `server.py` | Dynamically registers MCP tools from OpenAPI spec and handles API calls |
| **MCP Client** | `client.py` | Connects to LLM via LangChain and provides interactive chat interface |
| **OpenAPI Parser** | `openapi_parser.py` | Parses OpenAPI/Swagger specs from URLs or files, extracts endpoints |
| **Configuration** | `config.yaml` | Central configuration for API source, LLM settings, and customization |

---

## 📦 Installation

### Prerequisites

- Python 3.10 or higher
- An OpenAI API key (for the LLM client)

### Step 1: Clone the Repository

```bash
git clone https://github.com/Chrisliao0806/swagger_mcp_service.git
cd swagger_mcp_service
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini  # Optional: override model from config
```

---

## ⚙️ Configuration

All configuration is done through `generic_mcp/config.yaml`. Here's a breakdown of the key sections:

### API Configuration

```yaml
api:
  # OpenAPI specification source (choose one)
  openapi_url: "http://localhost:8000/openapi.json"  # Direct URL
  # openapi_url: "http://localhost:8000/docs"        # Swagger UI page (auto-detected)
  # openapi_file: "./openapi.json"                   # Local file (takes priority)
  
  # Base URL for API calls (used if not defined in OpenAPI spec)
  base_url: "http://localhost:8000"
  
  # Request timeout in seconds
  timeout: 30
```

### MCP Servers Configuration (Multi-Server Support)

```yaml
mcp_servers:
  # OpenAPI/Swagger type server
  - name: "My API Service"
    type: "openapi"
    enabled: true
    openapi:
      openapi_url: "http://localhost:8000/openapi.json"
      base_url: "http://localhost:8000"
    tool_generation:
      include_all: true
      snake_case_names: true

  # Third-party MCP server (auto tool discovery!)
  - name: "Fetch"
    type: "external"
    enabled: true
    command: "uvx"
    args: ["mcp-server-fetch"]
    # 🆕 No need to write description/tools_description!
    # They are automatically fetched from the MCP server
```

### Third-Party MCP Servers

You can connect to any third-party MCP server. **Tool descriptions are automatically discovered!**

```yaml
mcp_servers:
  # Example: mcp-server-fetch
  - name: "Fetch"
    type: "external"
    enabled: true
    command: "uvx"
    args: ["mcp-server-fetch"]

  # Example: Filesystem server
  - name: "Filesystem"
    type: "external"
    enabled: true
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]

  # Example: GitHub server with environment variables
  - name: "GitHub"
    type: "external"
    enabled: true
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"

  # Optional: Override auto-discovered descriptions
  - name: "Custom Server"
    type: "external"
    enabled: true
    command: "my-mcp-server"
    args: []
    description: "Custom description (optional)"
    tools_description: |  # Optional - overrides auto-discovery
      - **tool_name**: Custom tool description
```

### Tool Generation Options

```yaml
tool_generation:
  include_all: true                    # Include all endpoints
  exclude_endpoints: []                # Exclude specific endpoints
  snake_case_names: true               # Convert names to snake_case
  simplified_names: true               # Simplify tool names
  # tool_prefix: "myapi_"              # Optional prefix for all tools
```

Each OpenAPI server can also define request headers. Use full environment
variable references so credentials stay outside the configuration file:

```yaml
openapi:
  openapi_url: "https://example.com/openapi.json"
  base_url: "https://example.com"
  headers:
    Authorization: "${EXAMPLE_API_TOKEN}"
```

The service stops with a clear error when a referenced variable is missing.

The disabled Xquik sample in `generic_mcp/config.yaml` uses this mechanism with
`XQUIK_API_KEY`. It exposes an explicit read-first subset for tweet search,
tweet lookup, replies, trends, user search, and user lookup. Enable the sample
only after configuring that variable.

Xquik is an independent third-party service. Not affiliated with X Corp. "Twitter" and "X" are trademarks of X Corp.

### LLM Configuration

```yaml
llm:
  provider: "openai"
  model: "gpt-4.1-mini"
  temperature: 0
```

### System Prompt Customization

```yaml
system_prompt:
  template: |
    You are an AI assistant with access to the following API tools...
    
    Available Variables:
    - {api_name}: API title from OpenAPI spec
    - {api_description}: API description
    - {tools_summary}: Auto-generated tool documentation
```

---

## 🚀 Usage

### Quick Start
#### Option 1: Web Interface (Recommended) 🌐

1. **Start your target API server** (or use the included example):

```bash
cd api_swagger_example
uvicorn api_server:app --reload
```

2. **Configure the OpenAPI source** in `generic_mcp/config.yaml`:

```yaml
api:
  openapi_url: "http://localhost:8000/openapi.json"
  base_url: "http://localhost:8000"
```

3. **Launch the web server**:

```bash
cd generic_mcp
python web_server.py
```

#### Web Server

```bash
# Launch web interface with default config
python web_server.py

# Use custom configuration file
python web_server.py /path/to/my-config.yaml

# Set custom port (default: 8080)
export MCP_WEB_PORT=3000
python web_server.py

# Override LLM model
export OPENAI_MODEL=gpt-4o
python web_server.py
```

#### CLI Client

#### Web Interface
The web interface provides a beautiful, modern chat experience with:
- 💬 **Real-time Streaming** - Watch responses generate token by token
- 🔧 **Tool Call Visualization** - See when and how API tools are invoked
- 🎨 **Dark Theme** - Easy on the eyes, similar to Claude's interface
- 📝 **Markdown Support** - Rich formatting with code highlighting
- 📊 **Session Management** - Multiple conversation contexts

#### CLI Interface
4. **Open your browser** and visit: http://localhost:8080

#### Option 2: Command-Line Interface
3. **Run the interactive client**:

```bash
cd generic_mcp
python run.py
```

### Command-Line Options

```bash
# Run interactive client (default)
python run.py

# Use custom configuration file
python run.py --config /path/to/my-config.yaml

# Validate configuration and OpenAPI spec
python run.py --validate

# List all available tools
python run.py --list-tools

# Run server only (for debugging)
python run.py --server-only
```

### Example Interaction

```
============================================================
🤖 Procurement System API
============================================================
   Enterprise procurement management system...

👤 You: Show me recent purchase history

🤖 Assisweb_server.py            # 🌐 Web chat interface (FastAPI + SSE)
│   ├── run.py                   # CLI entry point
│   ├── server.py                # MCP server implementation
│   ├── client.py                # MCP client with LangChain
│   ├── openapi_parser.py        # OpenAPI specification parser
│   ├── config.yaml              # Configuration file
│   └── templates/
│       └── index.html           # Web UI templat-----------|
| PH001 | Laptop (Dell)   | 10       | NT$ 42,000 | Digital Co |
| PH002 | Laptop (Lenovo) | 5        | NT$ 52,000 | Tech Corp  |

------------------------------------------------------------

👤 You: Check inventory for Dell laptops

🤖 Assistant:
Dell Latitude 5540 Inventory Status:
- Available: 3 units
- Reserved: 2 units
- Location: Main Warehouse
```

---

## 📁 Project Structure

```
swagger_mcp_service/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── LICENSE                      # MIT License
│
├── generic_mcp/                 # Core MCP service
│   ├── __init__.py
│   ├── run.py                   # CLI entry point
│   ├── server.py                # MCP server implementation
│   ├── client.py                # MCP client with LangChain
│   ├── openapi_parser.py        # OpenAPI specification parser
│   └── config.yaml              # Configuration file
│
└── api_swagger_example/         # Example API server
    └── api_server.py            # FastAPI demo server
```


### 4. Web Interface Streaming

The web server uses Server-Sent Events (SSE) for real-time streaming:
1. **Token Streaming** - LLM responses stream character by character
2. **Tool Events** - `on_tool_start` and `on_tool_end` events show API calls
3. **Session Management** - Multiple conversation contexts with unique IDs
4. **Colored Logging** - Backend logs with timestamps and log levels
5. **Error Handling** - Graceful error messages displayed in UI
---

## 🔧 How It Works

### 1. OpenAPI Parsing

The `OpenAPIParser` class:
- Loads OpenAPI specs from URLs (including Swagger UI pages) or local files
- Automatically detects and extracts OpenAPI JSON from documentation pages
- Supports both OpenAPI 3.x and Swagger 2.0 formats

### 2. Dynamic Tool Generation

For each API endpoint, the system generates an MCP tool:

```
OpenAPI Endpoint                    →  MCP Tool
───────────────────────────────────────────────────
operationId / path+method           →  tool name (function name)
summary / description               →  tool description (docstring)
path parameters                     →  required parameters (in="path")
query parameters                    →  query parameters (in="query") 
request body properties             →  body parameters
```

### 3. Runtime Execution

When a tool is invoked:
1. Parameters are classified (path, query, body)
2. Path parameters are substituted in the URL
3. An HTTP request is made to the target API
4. Response is returned as JSON to the LLM

---

## 🧪 Example API Server

The `api_swagger_example/` directory contains a complete FastAPI demo server simulating an enterprise procurement system. It includes:

- 📋 **Purchase History** - Query past purchase records
- 📦 **Inventory Management** - Check stock and request items
- 🏢 **Supplier Management** - Query supplier information
- 🛒 **Product Catalog** - Browse products and prices
- 📝 **Purchase Requests** - Create and manage purchase requests
- 📄 **Purchase Orders** - Generate purchase orders

### Running the Example

```bash
cd api_swagger_example
uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
```

Access the Swagger UI at: http://localhost:8000/docs

---

## 🔌 Integration with Other Systems

### Using with External APIs

Simply update `config.yaml` to point to any OpenAPI-compliant API:

```yaml
mcp_servers:
  - name: "External API"
    type: "openapi"
    enabled: true
    openapi:
      openapi_url: "https://api.example.com/openapi.json"
      base_url: "https://api.example.com"
```

### Combining Multiple MCP Servers

You can combine OpenAPI servers with third-party MCP servers:

```yaml
mcp_servers:
  # Your internal API
  - name: "Internal API"
    type: "openapi"
    enabled: true
    openapi:
      openapi_url: "http://localhost:8000/openapi.json"
  
  # Web content fetching
  - name: "Fetch"
    type: "external"
    enabled: true
    command: "uvx"
    args: ["mcp-server-fetch"]
  
  # File system access
  - name: "Filesystem"
    type: "external"
    enabled: true
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "./data"]
```

### Connecting to Enterprise Systems

The service can integrate with:
- SAP systems (with OpenAPI gateway)
- Salesforce APIs
- AWS services with OpenAPI specs
- Any REST API with Swagger/OpenAPI documentation
- Third-party MCP servers from the community

---

## 🛡️ Error Handling

The system provides robust error handling:

- **Connection Errors**: Clear messages when API server is unreachable
- **HTTP Errors**: Detailed error responses with status codes
- **Parsing Errors**: Helpful suggestions when OpenAPI spec cannot be parsed
- **Validation Mode**: Pre-flight checks with `--validate` flag

---

## 📝 Customization Examples

### Filter Specific Endpoints

```yaml
tool_generation:
  include_all: false
  include_endpoints:
    - "get_purchase_history"
    - "create_purchase_order"
```

### Exclude Endpoints

```yaml
tool_generation:
  include_all: true
  exclude_endpoints:
    - "delete_all_data"
    - "/admin/*"
```

### Add Tool Prefix

```yaml
tool_generation:
  tool_prefix: "procurement_"
  # Results in: procurement_get_inventory, procurement_create_order, etc.
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers) - Reference servers and community resources
- [FastMCP](https://github.com/jlowin/fastmcp) - Simplified MCP server implementation
- [LangChain](https://github.com/langchain-ai/langchain) - LLM application framework
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework

---

<p align="center">
  Made with ❤️ for seamless API-to-LLM integration
</p>
