# agentic-mcp-framework

The goal of this project is to explore the integration between a modern agentic framework (**LangGraph**) and the **Model Context Protocol (MCP)**. 

## Architecture

The framework is divided into two main components:
1. **The Agent (LangGraph Client):** Reasons about tasks and decides when and how to invoke external tools.
2. **The MCP Server (The Tools):** Exposes traditional tools to the agent in a standardized format, acting as a bridge to external systems.

```text
agentic-mcp-framework/
├── agent/
│   └── react_agent.py        
|── mcp_server/
│   └── echo_mcp_server.py    
├── .env.example              
├── .gitignore
├── Dockerfile                
├── docker-compose.yml        
└── requirements.txt          
```

## Development Roadmap

- [x] **Architectural Setup:** Configuration of the Docker environment and the project architecture.
- [x] **Toy Example (Echo):** Basic communication between the agent and a local MCP server executing a simple "echo" script.
- [ ] **ASM Wrapper:** Development of a dedicated MCP server to wrap the REST APIs of `AsmetaS-web-service`.
- [ ] **Neuro-symbolic Showcase:** Testing and benchmarking the full interaction between the LLM and the ASM simulator.

## Toy example

The base infrastructure has been successfully validated through a "Toy Example" using an Echo tool. The framework correctly executes the complete ReAct loop:

1. **Thought**: The LLM processes the human message and determines it needs to use an external tool to fulfill the request.

2. **Action**: The agent issues a CallToolRequest targeting the echo_message function via the MCP protocol.

3. **Observation**: The isolated MCP server executes the script and returns the output to the agent's context.

4. **Response**: The agent incorporates the tool's execution result to generate the final output.

<img width="1256" height="533" alt="immagine" src="https://github.com/user-attachments/assets/fc8381f0-529d-42da-95a6-5befbada9b1f" />

## Quick Start (Docker)

The project is fully containerized to ensure isolation and reproducibility.

1. Clone the repository:
```bash
   git clone https://github.com/gallizzz/agentic-mcp-framework.git
```
2. Configure the environment variables:

   Create a copy of the file `.env.example` and name it `.env`, apply your Google AI Studio API Key (we use Gemini 3.5 flash for its free tier option) there: 
```plaintext
   GEMINI_API_KEY=your_google_ai_studio_api_key_here
```
3. Start the project:

   Build and start the containers, the LangGraph agent will start as the main process, calling and orchestrating the background MCP server.
```bash
   docker-compose up --build
```

