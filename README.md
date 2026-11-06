# agentic-mcp-framework

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)

Framework per l'integrazione di agenti basati su **LangGraph** e **Model Context Protocol (MCP)** con verifica formale deterministica a runtime tramite **AsmetaS** (Abstract State Machines).

Per i dettagli teorici, l'architettura software e le specifiche dei modelli ASM, consulta la [Wiki di Progetto](https://github.com/gallizzz/agentic-mcp-framework/wiki).

---

## Prerequisiti

Prima di iniziare, assicurati di avere installato sulla tua macchina:

* **Docker** e **Docker Compose**
* **Java (JRE 17+)** *(necessario sull'host per eseguire il server Java di AsmetaS)*
* Una **API Key di Google AI Studio** per accedere ai modelli Gemini ([ottienila qui](https://aistudio.google.com/))

Inoltre, il microservizio [`AsmetaS-web-service`](https://github.com/foselab/AsmetaS-web-service) deve essere presente (di norma clonato nella cartella adiacente `../AsmetaS-web-service`).

---

## Installazione e Configurazione

### 1. Clona il repository

```bash
git clone https://github.com/gallizzz/agentic-mcp-framework.git
cd agentic-mcp-framework
```

### 2. Configura le variabili d'ambiente

Copia il template `.env.example` in `.env`:

```bash
cp .env.example .env
```

Modifica il file `.env` inserendo la tua chiave API:

```env
GEMINI_API_KEY=inserisci_qui_la_tua_api_key_gemini
GEMINI_MODEL=gemini-flash-lite-latest
ASMETAS_URL=http://localhost:8080
USE_CASE=pillbox
```

### 3. Avvia il server formale AsmetaS

Avvia il server seguendo il README.md del progetto [AsmetaS-web-service](https://github.com/foselab/AsmetaS-web-service). Non serve caricare modelli a mano: il server MCP del caso di studio carica all'avvio i modelli elencati nella sua configurazione, leggendoli da `resources/`.

---

## Avvio dell'Agente con Docker

Costruisci l'immagine del container e avvia la sessione interattiva:

```bash
# 1. Costruzione dell'immagine
docker compose build

# 2. Avvio dell'agente interattivo
docker compose run --rm agentic-system
```

*(Il comando `run` con `--rm` collega direttamente stdin e stdout del terminale al container, permettendo di chattare con l'agente in tempo reale e rimuovendo il container una volta terminata la sessione).*

---

## Come Si Usa

Una volta avviato il container, vedrai comparire il prompt interattivo `You:`. Puoi dialogare con l'agente in linguaggio naturale. Gli esempi usano il caso di studio `pillbox`, un portapillole con dati sintetici.

### Esempi di comandi da provare:

* **Lettura dello stato (Bypass del Gate)**:
  ```text
  You: qual è lo stato attuale del portapillole?
  ```
* **Modifica verificata dagli ASM**:
  ```text
  You: sposta la prima dose di sumatriptan alle 17:00
  ```
  *(L'enforcer può approvare la richiesta, sostituire l'orario con uno ammesso, chiedere una nuova pianificazione o bloccarla).*

Per uscire dalla sessione digita `exit` oppure `quit`.

### Scenari senza LLM

Per esperimenti controllati, con il server AsmetaS attivo:

```bash
python use_cases/pillbox/run_scenario.py run use_cases/pillbox/scenarios/M1.json
```

---

## Struttura del Progetto

```text
core/                     Motore di orchestrazione generico (indipendente dal dominio)
  agent_graph.py          Entrypoint: grafo LangGraph Planner <-> Formal Gate
  config.py               UseCaseConfig e caricamento del caso di studio
enforcement/              Framework di enforcement: sessioni AsmetaS, preview, commit con ACK
  bootstrap.py            Entry point generici: server MCP ed esecutore di scenari
  mcp_facade.py           Tool MCP esposti all'agente
use_cases/                Casi di studio
  pillbox/                Portapillole (caso di riferimento)
    config.py             Server MCP e istruzioni per il Planner
    binding.py            Traduzione tra dati dell'applicazione e I/O degli ASM
    enforcement.json      Modelli da caricare e parametri fidati
    mcp_server.py         Server MCP del caso di studio
    run_scenario.py       Esecutore di scenari senza LLM
    scenarios/            Scenari JSON
resources/                Modelli ASM e librerie caricati su AsmetaS
```

---

## Configurazione

### Variabili d'Ambiente (`.env`)
Credenziali, parametri di connessione e selezione del caso di studio:

| Variabile | Default | Descrizione |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | *(obbligatoria)* | Chiave API di Google AI Studio. |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Modello LLM per il Planner (consigliato per evitare rate limit). |
| `ASMETAS_URL` | `http://localhost:8080` | URL del backend REST del simulatore AsmetaS. |
| `USE_CASE` | *(obbligatoria)* | Caso di studio da caricare da `use_cases/<nome>/config.py` (es. `pillbox`). Se manca, l'agente non parte. |

### Configurazione del Caso di Studio (`use_cases/<nome>/config.py`)
Ogni caso di studio definisce `USE_CASE = UseCaseConfig(...)` con:
* **`mcp_server_command`**: Comando stdio del server MCP del caso di studio.
* **`max_steps_per_turn`**: Numero massimo di passi del Planner per turno (default 3).
* **`planner_hints`**: Istruzioni di dominio aggiunte al prompt del Planner.

### Aggiungere un Nuovo Caso di Studio
1. Aggiungi i modelli ASM in `resources/models/`.
2. Crea `use_cases/<nome>/binding.py` con l'implementazione del `ModelBinding` (`enforcement/contracts.py`). `plan_description()` descrive le azioni ammesse e i `goals` al Planner, che non va istruito su questo nei `planner_hints`. `reason_glossary()` spiega i codici di motivo dell'enforcer, che tornano nel risultato come `reason_explanation`.
3. Crea la configurazione di enforcement (es. `enforcement.json`), con i modelli da caricare nella sezione `asmeta` e i parametri fidati.
4. Crea `use_cases/<nome>/mcp_server.py`, che chiama `enforcement.bootstrap.run_mcp_server` con il binding e la configurazione. Facoltativamente crea `run_scenario.py` con `run_scenario_cli`.
5. Crea `use_cases/<nome>/config.py` con `USE_CASE = UseCaseConfig(...)`.
6. Imposta `USE_CASE=<nome>` nel `.env` e avvia l'agente.

---

## Documentazione e Wiki

Tutti i dettagli teorici, le specifiche formali di sicurezza e le guide per estendere il framework ad altri domini sono disponibili nella Wiki:

* [Architettura & Framework](https://github.com/gallizzz/agentic-mcp-framework/wiki/Architettura-&-Framework)
* [Formal Verification con AsmetaS](https://github.com/gallizzz/agentic-mcp-framework/wiki/Formal-Verification-con-AsmetaS)
* [Integrazioni e Nuovi Domini](https://github.com/gallizzz/agentic-mcp-framework/wiki/Integrazioni)
