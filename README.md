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


### Guida Passo-Passo all'Avvio e Collaudo

Trovi la guida per il testing del servizio MCP a questo [link](https://github.com/gallizzz/agentic-mcp-framework/wiki/Setup-e-Validazione-End%E2%80%90to%E2%80%90End-di-AsmetaS-Runtime-&-Server-MCP)


### Contratto Agent-to-Agent (A2A)
La specifica A2A per l'agente deterministico `AsmetaSEnforcerGuard` è definita nel file [agent-card.json](file:///home/galliz/Documenti/Progetti/agentic-mcp-framework/mcp_server/asmetas/agent-card.json).

---

## Documentazione & Wiki

Per informazioni dettagliate sull'architettura del sistema, sulle implementazioni e sulla roadmap, consulta la sezione [WIKI](https://github.com/gallizzz/agentic-mcp-framework/wiki).
