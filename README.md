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
```

### 3. Avvia il server formale AsmetaS

Segui il README.md del progetto [AsmetaS-web-service](https://github.com/foselab/AsmetaS-web-service) fino ad avviare lo script main.py del toy_example.

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

## Configurazione (.env e agent/config.py)

### Variabili d'Ambiente (`.env`)
Solo credenziali di autenticazione e parametri di connessione di rete:

| Variabile | Default | Descrizione |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | *(obbligatoria)* | Chiave API di Google AI Studio. |
| `GEMINI_MODEL` | `gemini-flash-lite-latest` | Modello LLM per il Planner (consigliato per evitare rate limit). |
| `ASMETAS_URL` | `http://localhost:8080` | URL del backend REST del simulatore AsmetaS. |

### Costanti di Configurazione (`agent/config.py`)
Tutti i parametri statici, configurazioni dei server MCP, mappature di dominio e politiche del Formal Gate sono centralizzati in `agent/config.py`:
* **`ASMETA_MODEL_NAME`**: Nome del modello formale registrato su AsmetaS (`SafetyEnforcerModel.asm`).
* **`ASMETAS_MCP_COMMAND`** e **`ENVIRONMENT_MCP_COMMAND`**: Comandi di esecuzione stdio per i server MCP (AsmetaS guard e ambiente).
* **`ACTION_MAPPING`**: Mappatura tra le azioni candidate dell'ambiente e quelle del modello ASM (`{"KEEP": "IDLE"}`).
* **`DEFAULT_MONITORED_VARIABLES`**: Valori di default per le variabili sensoriali monitorate.
* **`GATE_POLICY`** e **`ERROR_POLICY`**: Politiche di shielding e fail-safe del Formal Gate.

---

## Documentazione e Wiki

Tutti i dettagli teorici, le specifiche formali di sicurezza e le guide per estendere il framework ad altri domini sono disponibili nella Wiki:

* [Architettura & Framework](https://github.com/gallizzz/agentic-mcp-framework/wiki/Architettura-&-Framework)
* [Formal Verification con AsmetaS](https://github.com/gallizzz/agentic-mcp-framework/wiki/Formal-Verification-con-AsmetaS)
* [Integrazioni e Nuovi Domini](https://github.com/gallizzz/agentic-mcp-framework/wiki/Integrazioni)
* [Esempi e Scenari](https://github.com/gallizzz/agentic-mcp-framework/wiki/Esempi-‐-Veicolo)
