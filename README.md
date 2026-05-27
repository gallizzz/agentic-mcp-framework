# agentic-mcp-framework

The goal of this project is to explore the integration between a modern agentic framework (**LangGraph**) and the **Model Context Protocol (MCP)**. 

## Architecture

The framework is divided into two main components:
1. **The Agent (LangGraph Client):** Reasons about tasks and decides when and how to invoke external tools.
2. **The MCP Server (The Tools):** Exposes traditional tools to the agent in a standardized format, acting as a bridge to external systems.

## Development Roadmap

- [x] **Architectural Setup:** Configuration of the Docker environment and the ReAct pattern.
- [ ] **Toy Example (Echo):** Initial Proof of Concept. Basic communication between the agent and a local MCP server executing a simple "echo" script.
- [ ] **ASM Wrapper:** Development of a dedicated MCP server to wrap the REST APIs of `AsmetaS-web-service`.
- [ ] **Neuro-symbolic Showcase:** Testing and benchmarking the full interaction between the LLM and the ASM simulator.

## Quick Start (Docker)

The project is fully containerized to ensure isolation and reproducibility.

1. Clone the repository:
```bash
   git clone [https://github.com/gallizzz/agentic-mcp-framework.git](https://github.com/gallizzz/agentic-mcp-framework.git)
```
2. [TODO]