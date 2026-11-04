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
USE_CASE=vehicle
```

### 3. Avvia il server formale AsmetaS

Avvia il server seguendo il README.md del progetto [AsmetaS-web-service](https://github.com/foselab/AsmetaS-web-service). Non serve caricare modelli a mano: l'agente carica all'avvio quelli del caso di studio scelto, leggendoli da `resources/`.

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

Una volta avviato il container, vedrai comparire il prompt interattivo `You:`. Puoi dialogare con l'agente in linguaggio naturale inviando comandi di guida o richieste di telemetria.

### Esempi di comandi da provare:

* **Lettura telemetria (Bypass del Gate)**:
  ```text
  You: qual'è la telemetria attuale del veicolo?
  ```
* **Accelerazione con incremento numerico**:
  ```text
  You: accelera di 10 km/h
  ```
* **Comando con vincolo di sicurezza formale (Keep Right)**:
  ```text
  You: accelera, la corsia di destra è libera
  ```
  *(Il guardiano AsmetaS intercetta la violazione e applica lo shielding forzando lo spostamento a destra).*
* **Spostamento di corsia o arresto**:
  ```text
  You: puoi spostarti a destra?
  You: ferma il veicolo
  ```

Per uscire dalla sessione digita `exit` oppure `quit`.

---

## Struttura del Progetto

```text
core/                     Motore di orchestrazione generico (indipendente dal dominio)
  agent_graph.py          Entrypoint: grafo LangGraph Planner -> Formal Gate -> Environment
  config.py               UseCaseConfig e caricamento del caso di studio
  mcp_server/             Adattatore MCP verso AsmetaS-web-service
use_cases/                Casi di studio
  vehicle/                Emulatore dell'auto (caso di riferimento)
    config.py             Modello ASM, server MCP dell'ambiente, mappature e politiche
    vehicle_mcp_server.py Ambiente simulato esposto via MCP
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
| `USE_CASE` | *(obbligatoria)* | Caso di studio da caricare da `use_cases/<nome>/config.py` (es. `vehicle`). Se manca, l'agente non parte. |
| `READ_ONLY_TOOLS` | *(vuoto)* | Tool dell'ambiente (separati da virgola) che non passano dal Formal Gate, per server MCP privi dell'annotazione `readOnlyHint`. |
| `SYSTEM_PROMPT` | *(generato)* | Sovrascrive il system prompt del Planner. |

### Configurazione del Caso di Studio (`use_cases/<nome>/config.py`)
Ogni caso di studio definisce `USE_CASE = UseCaseConfig(...)` con:
* **`asm_model_name`**: Nome del modello formale registrato su AsmetaS (per il veicolo `vehicleEnforcer.asm`).
* **`asm_sources`**: File `.asm` di `resources/` che l'agente carica su AsmetaS all'avvio (modello e libreria).
* **`environment_mcp_command`**: Comando stdio del server MCP dell'ambiente.
* **`default_safe_action`**: Azione eseguita in modalità fail-safe; deve essere accettata sia dall'ambiente sia dal dominio `inputAction` dell'ASM.
* **`action_mapping`**: Mappatura tra le azioni dell'ambiente e quelle del modello ASM (per il veicolo `{"KEEP": "IDLE"}`).
* **`default_monitored_variables`**: Valori di default per le variabili sensoriali monitorate.
* **`gate_policy`** e **`error_policy`**: Politiche di shielding/replan e fail-safe/fail-stop del Formal Gate.

### Aggiungere un Nuovo Caso di Studio
1. Crea `use_cases/<nome>/` con un server MCP dell'ambiente. Annota i tool di sola lettura con `ToolAnnotations(readOnlyHint=True)`: tutti gli altri passano obbligatoriamente dal Formal Gate.
2. Crea `use_cases/<nome>/config.py` con `USE_CASE = UseCaseConfig(...)`.
3. Carica il modello ASM su `AsmetaS-web-service`: il modello deve esporre la variabile monitorata `inputAction` e la variabile di output `outAction`.
4. Imposta `USE_CASE=<nome>` nel `.env` e avvia l'agente.

---

## Documentazione e Wiki

Tutti i dettagli teorici, le specifiche formali di sicurezza e le guide per estendere il framework ad altri domini sono disponibili nella Wiki:

* [Architettura & Framework](https://github.com/gallizzz/agentic-mcp-framework/wiki/Architettura-&-Framework)
* [Formal Verification con AsmetaS](https://github.com/gallizzz/agentic-mcp-framework/wiki/Formal-Verification-con-AsmetaS)
* [Integrazioni e Nuovi Domini](https://github.com/gallizzz/agentic-mcp-framework/wiki/Integrazioni)
* [Esempi e Scenari](https://github.com/gallizzz/agentic-mcp-framework/wiki/Esempi-‐-Veicolo)
