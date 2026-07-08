# agentic-mcp-framework

The goal of this project is to explore the integration between a modern agentic framework (**LangGraph**) and the **Model Context Protocol (MCP)**. 

## Architecture

The framework is divided into two main components:
1. **The Agent (LangGraph Client):** Reasons about tasks and decides when and how to invoke external tools.
2. **The MCP Server (The Tools):** Exposes traditional tools to the agent in a standardized format, acting as a bridge to external systems.

### The ReAct Paradigm

The agent in [react_agent.py](agent/react_agent.py) is implemented using the **ReAct (Reasoning + Acting)** paradigm:
* **Reasoning:** The LLM (Gemini 3.5 Flash) evaluates the user input to determine if external information or action is needed.
* **Acting:** The agent executes specific tools provided by the connected MCP Servers (such as checking inventories or adding pets).
* **Observing:** The outputs of these tools are sent back to the LLM as observations, allowing it to reason again and decide whether to call another tool or return the final answer.

```text
agentic-mcp-framework/
├── agent/
│   └── react_agent.py        
├── mcp_server/
│   ├── echo_mcp_server.py    
│   └── petstore_mcp_server.py
├── .env.example              
├── .gitignore
├── Dockerfile                
├── docker-compose.yml        
└── requirements.txt          
```

## Development Roadmap

- [x] **Architectural Setup:** Configuration of the Docker environment and the project architecture.
- [x] **Toy Example (Echo):** Basic communication between the agent and a local MCP server executing a simple "echo" script.
- [x] **Petstore API Wrapper:** Development of a dedicated MCP server wrapping the REST APIs of `petstore.swagger.io`.
- [x] **Interactive CLI:** Interactive console agent supporting dynamic user requests with clean formatting.
- [ ] **ASM Wrapper:** Development of a dedicated MCP server to wrap the REST APIs of `AsmetaS-web-service`.
- [ ] **Neuro-symbolic Showcase:** Testing and benchmarking the full interaction between the LLM and the ASM simulator.

## Integrations

### 1. Echo MCP Server
A simple local server to test the base configuration. Exposes a single tool (`echo_message`) that prints the agent's message back to the stdout.

### 2. Swagger Petstore MCP Server
A complete REST API wrapper for `petstore.swagger.io` written with **FastMCP** and `requests`. It exposes the following tools:
*   `get_store_inventory`: Get status-based pet inventory counts.
*   `find_pets_by_status`: Find pets matching status (`available`, `pending`, `sold`).
*   `get_pet_by_id`: Fetch pet details by numeric ID.
*   `add_pet`: Add a new pet to the database.
*   `delete_pet`: Delete a pet by its numeric ID.

---

## Quick Start (Docker)

The project is fully containerized to ensure isolation and reproducibility.

### 1. Configure the environment variables
Create a copy of the `.env.example` file and name it `.env`, then add your Google AI Studio API Key:
```plaintext
GEMINI_API_KEY=your_google_ai_studio_api_key_here
```

### 2. Start the interactive agent
Build and start the agent in interactive CLI mode using Docker Compose:
```bash
docker-compose run --rm agentic-system
```
*(Using `run` instead of `up` connects your terminal's stdin/stdout to the container so you can chat with the agent in real-time).*

### 3. Example Queries
Try typing some requests when the agent is ready:
*   `What is the current inventory in the pet store?`
*   `Find all sold pets in the store.`
*   `Add a new pet named "Rocky" with status "available".`
*   `Echo the message "Hello, MCP!"` (calls the Echo server).


