# agentic-mcp-framework

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)

Framework for integrating agents based on **LangGraph** and the **Model Context Protocol (MCP)** with deterministic runtime formal verification through **AsmetaS** (Abstract State Machines).

For the theoretical background, the software architecture and the ASM model specifications, see the [Project Wiki](https://github.com/gallizzz/agentic-mcp-framework/wiki).

---

## Prerequisites

Before you start, make sure the following are installed on your machine:

* **Docker** and **Docker Compose**
* **Java (JRE 17+)** *(required on the host to run the AsmetaS Java server)*
* A **Google AI Studio API key** to access the Gemini models ([get one here](https://aistudio.google.com/))

The [`AsmetaS-web-service`](https://github.com/foselab/AsmetaS-web-service) microservice must also be available (usually cloned into the sibling folder `../AsmetaS-web-service`).

---

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/gallizzz/agentic-mcp-framework.git
cd agentic-mcp-framework
```

### 2. Configure the environment variables

Copy the `.env.example` template to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and insert your API key:

```env
GEMINI_API_KEY=insert_your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
ASMETAS_URL=http://localhost:8080
USE_CASE=pillbox
```

### 3. Start the AsmetaS formal server

Start the server by following the README.md of the [AsmetaS-web-service](https://github.com/foselab/AsmetaS-web-service) project. You do not need to upload models by hand: at startup, the use case's MCP server uploads the models listed in its configuration, reading them from `resources/`.

---

## Running the Agent with Docker

Build the container image and start the interactive session:

```bash
# 1. Build the image
docker compose build

# 2. Start the interactive agent
docker compose run --rm agentic-system
```

*(The `run` command with `--rm` attaches the terminal's stdin and stdout directly to the container, so you can chat with the agent in real time, and removes the container when the session ends.)*

---

## Usage

Once the container is running, the interactive `You:` prompt appears. You can talk to the agent in natural language. The examples use the `pillbox` use case, a pill organizer with synthetic data.

### Example commands to try:

* **Reading the state (Gate bypass)**:
  ```text
  You: what is the current state of the pillbox?
  ```
* **Change verified by the ASMs**:
  ```text
  You: move the first sumatriptan dose to 17:00
  ```
  *(The enforcer can approve the request, replace the time with an allowed one, ask for a new plan, or block it.)*

To leave the session, type `exit` or `quit`.

### Scenarios without the LLM

For controlled experiments, with the AsmetaS server running:

```bash
python use_cases/pillbox/run_scenario.py run use_cases/pillbox/scenarios/M1.json
```

---

## Project Structure

```text
core/                     Generic orchestration engine (domain-independent)
  agent_graph.py          Entrypoint: LangGraph graph Planner <-> Formal Gate
  config.py               UseCaseConfig and use case loading
enforcement/              Enforcement framework: AsmetaS sessions, preview, commit with ACK
  bootstrap.py            Generic entry points: MCP server and scenario runner
  mcp_facade.py           MCP tools exposed to the agent
use_cases/                Use cases
  pillbox/                Pill organizer (reference use case)
    config.py             MCP server and Planner instructions
    binding.py            Translation between application data and ASM I/O
    enforcement.json      Models to upload and trusted parameters
    mcp_server.py         MCP server of the use case
    run_scenario.py       Scenario runner without the LLM
    scenarios/            JSON scenarios
resources/                ASM models and libraries uploaded to AsmetaS
```

---

## Configuration

### Environment Variables (`.env`)
Credentials, connection parameters and use case selection:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | *(required)* | Google AI Studio API key. |
| `GEMINI_MODEL` | *(required)* | LLM model for the Planner (e.g. `gemini-3.5-flash-lite`). If missing, the agent does not start. |
| `ASMETAS_URL` | *(required)* | URL of the AsmetaS REST backend (e.g. `http://localhost:8080`). Single source of the address: if missing, the agent does not start. |
| `USE_CASE` | *(required)* | Use case to load from `use_cases/<name>/config.py` (e.g. `pillbox`). If missing, the agent does not start. |

### Use Case Configuration (`use_cases/<name>/config.py`)
Each use case defines `USE_CASE = UseCaseConfig(...)` with:
* **`mcp_server_command`**: stdio command of the use case's MCP server.
* **`max_steps_per_turn`**: maximum number of Planner steps per turn (default 3).
* **`planner_hints`**: domain instructions appended to the Planner prompt (the pillbox reads them from `use_cases/pillbox/planner_hints.md`). The generic prompt is in `core/planner_prompt.md`.

### Adding a New Use Case
1. Add the ASM models to `resources/models/`.
2. Create `use_cases/<name>/binding.py` implementing `ModelBinding` (`enforcement/contracts.py`). `plan_description()` describes the allowed actions and the `goals` to the Planner, so the `planner_hints` must not cover them. `reason_glossary()` explains the enforcer's reason codes, which come back in the result as `reason_explanation`.
3. Create the enforcement configuration (e.g. `enforcement.json`), with the models to upload in the `asmeta` section and the trusted parameters.
4. Create `use_cases/<name>/mcp_server.py`, which calls `enforcement.bootstrap.run_mcp_server` with the binding and the configuration. Optionally create `run_scenario.py` with `run_scenario_cli`.
5. Create `use_cases/<name>/config.py` with `USE_CASE = UseCaseConfig(...)`.
6. Set `USE_CASE=<name>` in `.env` and start the agent.

---

## Documentation and Wiki

The theoretical details, the formal safety specifications and the guides for extending the framework to other domains are available in the Wiki:

* [Architecture & Framework](https://github.com/gallizzz/agentic-mcp-framework/wiki/Architettura-&-Framework)
* [Formal Verification with AsmetaS](https://github.com/gallizzz/agentic-mcp-framework/wiki/Formal-Verification-con-AsmetaS)
* [Integrations and New Domains](https://github.com/gallizzz/agentic-mcp-framework/wiki/Integrazioni)
