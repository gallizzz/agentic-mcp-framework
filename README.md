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
* `Mantieni la velocità, la corsia di destra è occupata (rightLaneFree=false).` (Azione approvata)
* `Accelera a tutta velocità (FASTER), la corsia di destra è libera (rightLaneFree=true).` (Violazione sanitizzata a LANE_RIGHT)
* `Qual è la telemetria attuale del veicolo?`

---

## Server MCP AsmetaS Formal Guard (Fase 2)

Il server MCP `mcp_server/asmetas/asmetas_mcp_server.py` incapsula il simulatore runtime `AsmetaS@run.time` (`foselab/AsmetaS-web-service`) per la verifica formale a runtime e la sanitizzazione delle azioni degli agenti.


### Guida all'Avvio e Collaudo

Trovi la guida per il testing del servizio MCP a questo [link](https://github.com/gallizzz/agentic-mcp-framework/wiki/Setup-e-Validazione-End%E2%80%90to%E2%80%90End-di-AsmetaS-Runtime-&-Server-MCP)


### Contratto Agent-to-Agent (A2A)
La specifica A2A per l'agente deterministico `AsmetaSEnforcerGuard` è definita nel file [agent-card.json](file:///home/galliz/Documenti/Progetti/agentic-mcp-framework/mcp_server/asmetas/agent-card.json).

## Integrazione LangGraph (Formal Gate - Fase 3)

Il sistema implementa un'architettura **Shielded Agent** tramite **LangGraph**:

```
Planner (LLM) ---> Formal Gate (AsmetaS) ---> Environment (Action)
```

1. **Planner (LLM)**: Pianifica la mossa e propone l'azione candidata.
2. **Formal Gate (Nodo Deterministico AsmetaS)**: Intercetta l'azione candidata prima che raggiunga l'ambiente, invoca `sanitise_action` sul server MCP AsmetaS e verifica la conformità con il modello formale ASM:
   - Se `APPROVED`: invia l'azione inalterata all'ambiente.
   - Se `VIOLATION` (Shielding): riscrive l'azione con la variante sicura calcolata formalmente da AsmetaS prima dell'esecuzione.
   - Se `VIOLATION` (Re-planning): inietta il feedback formale nel contesto del Planner per una ripianificazione guidata da vincoli.
   - Se `ERROR` / timeout: applica la policy di fail-safe configurata (es. comando `STOP`).
3. **Environment (MCP Tools)**: Esegue l'azione autorizzata/sanitizzata sul server MCP attuatore (`VehicleActuatorServer`).

---

## Documentazione & Wiki

Per informazioni dettagliate sull'architettura del sistema, sulle implementazioni e sulla roadmap, consulta la sezione [WIKI](https://github.com/gallizzz/agentic-mcp-framework/wiki).
