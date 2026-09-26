# agentic-mcp-framework

L'obiettivo di questo progetto è esplorare l'integrazione tra un moderno framework agentico (**LangGraph**) e il **Model Context Protocol (MCP)**.

## Avvio Rapido (Docker)

Il progetto è completamente containerizzato per garantire isolamento e riproducibilità.

### 1. Configurazione delle variabili d'ambiente
Crea una copia del file `.env.example` denominandola `.env`, quindi inserisci la tua API Key di Google AI Studio:
```plaintext
GEMINI_API_KEY=tua_api_key_google_ai_studio_qui
```

### 2. Avvio dell'agente interattivo
Esegui la build e avvia l'agente in modalità CLI interattiva utilizzando Docker Compose:
```bash
docker-compose run --rm agentic-system
```
*(Utilizzando `run` anziché `up`, lo stdin/stdout del tuo terminale viene collegato al container consentendoti di chattare con l'agente in tempo reale).*

### 3. Esempi di Query
Prova a digitare alcune richieste quando l'agente è pronto:
* `Qual è l'inventario attuale nel pet store?`
* `Trova tutti i pet venduti nello store.`
* `Aggiungi un nuovo pet chiamato "Rocky" con stato "available".`
* `Fai l'echo del messaggio "Ciao, MCP!"` (invoca l'Echo server).

---

## Server MCP AsmetaS Formal Guard (Fase 2)

Il server MCP `mcp_server/asmetas/asmetas_mcp_server.py` incapsula il simulatore runtime `AsmetaS@run.time` (`foselab/AsmetaS-web-service`) per la verifica formale a runtime e la sanitizzazione delle azioni degli agenti.

---

### Guida Passo-Passo all'Avvio e Collaudo

#### Passaggio 1: Installazione delle Dipendenze
Assicurarsi che l'ambiente virtuale sia attivo e installare i pacchetti necessari:
```bash
pip install -r requirements.txt
```

#### Passaggio 2: Avvio di AsmetaS Web Service
Il server MCP comunica via HTTP con il servizio web di AsmetaS (`foselab/AsmetaS-web-service`).
1. Avviare il container/servizio web AsmetaS verificando che sia in esecuzione sulla porta `8080`.
2. Verificare l'accessibilità dell'endpoint:
   ```bash
   curl -s http://localhost:8080/running-models
   ```
   *(Opzionale: se AsmetaS è in esecuzione su un'altra porta o URL, impostare la variabile d'ambiente `export ASMETAS_URL=http://localhost:8080`).*

#### Passaggio 3: Testing Interattivo con MCP Inspector
Per collaudare i tool MCP prima dell'integrazione con i nodi LangGraph:
1. Eseguire l'MCP Inspector tramite `npx`:
   ```bash
   npx @modelcontextprotocol/inspector python3 mcp_server/asmetas/asmetas_mcp_server.py
   ```
   *(Nota: se si utilizza un virtualenv locale, specificare il path dell'interprete: `npx @modelcontextprotocol/inspector .venv/bin/python mcp_server/asmetas/asmetas_mcp_server.py`)*.

2. **Flusso di Test raccomandato nell'Inspector**:
   - **Tool 1: `start_enforcer`**
     - Argomenti: `{"asm_name": "SafetyEnforcerModel.asm"}`
     - *Verifica*: Conferma dell'avvio e restituzione dell'`execution_id` di sessione.
   - **Tool 2: `sanitise_action` (Verdetto APPROVED)**
     - Argomenti: `{"monitored_variables": {"inputAction": "IDLE", "rightLaneFree": "true"}}`
     - *Verifica*: Verdetto `APPROVED` e azione inalterata (`IDLE`).
   - **Tool 3: `sanitise_action` (Verdetto VIOLATION)**
     - Argomenti: `{"monitored_variables": {"inputAction": "FASTER", "rightLaneFree": "false"}}`
     - *Verifica*: Verdetto `VIOLATION` con azione sanitizzata dal guard formale e relativo feedback informativo.
   - **Tool 4: `stop_enforcer`**
     - Argomenti: `{}`
     - *Verifica*: Chiusura corretta della sessione AsmetaS.

---

### Configurazione Stdio Client per LangGraph / MCP Client
Per registrare il server `asmetas-formal-guard` in un client MCP (es. `MultiServerMCPClient` di LangChain/LangGraph):

```json
{
  "mcpServers": {
    "asmetas-formal-guard": {
      "command": "python",
      "args": ["mcp_server/asmetas/asmetas_mcp_server.py"],
      "env": {
        "ASMETAS_URL": "http://localhost:8080"
      }
    }
  }
}
```

---

### Contratto Agent-to-Agent (A2A)
La specifica A2A per l'agente deterministico `AsmetaSEnforcerGuard` è definita nel file [agent-card.json](file:///home/galliz/Documenti/Progetti/agentic-mcp-framework/mcp_server/asmetas/agent-card.json).

---

## Documentazione & Wiki

Per informazioni dettagliate sull'architettura del sistema, sulle implementazioni e sulla roadmap, consulta la sezione [WIKI](https://github.com/gallizzz/agentic-mcp-framework/wiki).
