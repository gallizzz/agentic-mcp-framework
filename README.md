# agentic-mcp-framework

The goal of this project is to explore the integration between a modern agentic framework (**LangGraph**) and the **Model Context Protocol (MCP)**.


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

## Documentation & Wiki

For detailed information about the system architecture, implementations, and roadmap, please see the following [WIKI](https://github.com/gallizzz/agentic-mcp-framework/wiki) section.   
