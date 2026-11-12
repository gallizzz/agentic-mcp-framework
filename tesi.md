UNIVERSITÀ DEGLI STUDI DI BERGAMO

+---------------------------------------------------------------------------------------+
| Dipartimento di\                                                                      |
| Ingegneria Gestionale, dell\'Informazione e della Produzione                          |
+=====================================+=================================================+
| Corso di laurea in\                                                                   |
| Ingegneria Informatica                                                                |
+---------------------------------------------------------------------------------------+
| Classe n. L-8 - Ingegneria dell'Informazione                                          |
+---------------------------------------------------------------------------------------+
| Runtime enforcement delle azioni di agenti LLM mediante Abstract State Machines       |
+-------------------------------------+-------------------------------------------------+
| Candidato:\                         | Relatore:\                                      |
| *Lorenzo Gallizioli*                | *Chiar.ma Prof.ssa Patrizia Scandurra*          |
+-------------------------------------+-------------------------------------------------+
| Matricola n.                        |                                                 |
|                                     |                                                 |
| 1087404                             |                                                 |
+-------------------------------------+-------------------------------------------------+
|                                     |                                                 |
+-------------------------------------+-------------------------------------------------+
|                                     |                                                 |
+-------------------------------------+-------------------------------------------------+
| Anno Accademico                                                                       |
|                                                                                       |
| 2025/2026                                                                             |
+---------------------------------------------------------------------------------------+

Sommario

L\'impiego di modelli Large Language Model (LLM) all'interno di agenti
autonomi consente di gestire compiti complessi mediante pianificazione
in linguaggio naturale. Poiché tali agenti possono ora selezionare tool
esterni ed eseguire azioni direttamente sull'ambiente, diventa
necessario controllarne il comportamento a runtime. La natura
probabilistica degli LLM, la loro vulnerabilità alle allucinazioni e
l'insufficienza dei vincoli definiti unicamente nei prompt o delle
verifiche ex-post, ovvero successive all\'esecuzione delle azioni,
possono infatti condurre a danni irreversibili, soprattutto in contesti
safety-critical.

Per affrontare questo problema, la tesi propone un design pattern
architetturale per agenti basato sul paradigma Proposer-Verifier per la
sanitizzazione delle azioni degli agenti LLM prima di attuarle. Il
pattern si concretizza nell\'uso di una tecnica di runtime enforcement
basata sul metodo formale delle macchine a stati astratti (Abstract
State Machines, ASM). L'orchestrazione dello stato e dei flussi ciclici
è gestita tramite il framework agentico LangGraph, mentre la
comunicazione tra l'agente e il servizio di simulazione di modelli ASM,
AsmetaS, avviene attraverso il Model Context Protocol (MCP).

Il componente centrale è il Formal Gate Node, interposto tra l'agente e
l'ambiente di esecuzione. Il Formal Gate intercetta le azioni candidate
e ne valuta la conformità rispetto alle precondizioni e ai vincoli di
sicurezza codificati nel modello ASM. Il Formal Gate realizza una
verifica a runtime preventiva controllando l'azione candidata prima che
venga eseguita e, se necessario, applicando una delle due politiche
previste: lo shielding, che sostituisce l'azione non valida con la
correzione ammissibile più vicina calcolata dal modello ASM, oppure il
re-planning con invio all\'agente LLM di un feedback correttivo per
riformulare la pianificazione dell\'azione.

La valutazione del pattern è stata condotta attraverso l\'applicazione
ad alcuni casi di studio in ambienti simulati.

[Indice]{.mark}

[]{.mark}[1. Introduzione[]{.mark}](#introduzione) []{.mark}

[[1.1 Problema affrontato]{.mark}](#problema-affrontato)

[[1.2 Stato dell'arte]{.mark}](#stato-dellarte)

[1.3 Contesto tecnologico[]{.mark}](#contesto-tecnologico) []{.mark}

[[1.3.1 Dominio probabilistico (Ecosistema
AI)]{.mark}](#dominio-probabilistico-ecosistema-ai) []{.mark}

[[1.3.2 Dominio deterministico (metodi formali e
ASMETA)]{.mark}](#dominio-deterministico-metodi-formali-e-asmeta)
[]{.mark}

[[1.4 Soluzione proposta]{.mark}](#soluzione-proposta)

[2. Nozioni di background](#nozioni-di-background)

[2.1 Paradigma ReAct](#paradigma-react)

[2.2 Framework agentici](#framework-agentici)

[2.3 Protocolli di interconnessione](#protocolli-di-interconnessione)

[2.4 Valutazione e sicurezza degli
agenti](#valutazione-e-sicurezza-degli-agenti)

[2.5 LLM Symbolic Reasoning](#llm-symbolic-reasoning)

[2.6 Feedback Loop e limiti
all'auto-correzione](#feedback-loop-e-limiti-allauto-correzione)

[[2.7 Agent design pattern]{.mark} per la
sicurezza[]{.mark}](#agent-design-pattern-per-la-sicurezza) []{.mark}

[[2.7.1 Multimodal Guardrails]{.mark}](#multimodal-guardrails) []{.mark}

[[2.7.2 Cross-Reflection per il
re-planning]{.mark}](#cross-reflection-per-il-re-planning) []{.mark}

[[2.7.3 Agent adapter per
l'interoperabilità]{.mark}](#agent-adapter-per-linteroperabilità)
[]{.mark}

[2.8 Sistemi auto-adattativi e ciclo
MAPE-K[]{.mark}](#sistemi-auto-adattativi-e-ciclo-mape-k) []{.mark}

[3. Idea Progettuale](#idea-progettuale)

[3.1 Obiettivi](#obiettivi)

[3.1.1 Runtime Enforcement e I/O
Sanitization](#runtime-enforcement-e-io-sanitization)

[3.1.2 Gestione dello stato e controllo deterministico del
flusso](#gestione-dello-stato-e-controllo-deterministico-del-flusso)

[3.1.3 Costruire un\'infrastruttura
modulare](#costruire-uninfrastruttura-modulare)

[3.1.4 Accessibilità naturale a metodi
formali](#accessibilità-naturale-a-metodi-formali)

[3.2 Piano d'azione](#piano-dazione)

[3.2.1 Containerizzazione e validazione dell\'infrastruttura di
base](#containerizzazione-e-validazione-dellinfrastruttura-di-base)

[3.2.2 Implementazione del server MCP](#implementazione-del-server-mcp)

[3.2.3 Design dei prompt e logica di traduzione
neuro-simbolica](#design-dei-prompt-e-logica-di-traduzione-neuro-simbolica)

[3.2.4 Sviluppo del grafo LangGraph](#sviluppo-del-grafo-langgraph)

[[4.]{.mark} Progettazione e
implementazione](#progettazione-e-implementazione)

[[4.1 Architettura
neuro-simbolica]{.mark}](#architettura-neuro-simbolica)

[[4.2 Anatomia dei nodi LangGraph]{.mark}](#anatomia-dei-nodi-langgraph)

[[4.2.1 PlannerNode]{.mark}](#plannernode)

[[4.2.2 FormalGateNode]{.mark}](#formalgatenode)

[[4.2.3 Instradamento dopo il Formal
Gate]{.mark}](#instradamento-dopo-il-formal-gate)

[4.3 Mappa dei protocolli e topologia di
comunicazione[]{.mark}](#mappa-dei-protocolli-e-topologia-di-comunicazione)
[]{.mark}

[4.4 Ciclo di esecuzione e schema
enforcement[]{.mark}](#ciclo-di-esecuzione-e-schema-enforcement)
[]{.mark}

[4.5 Framework di enforcement[]{.mark}](#framework-di-enforcement)
[]{.mark}

[4.6 Separazione tra motore generico e caso di
studio[]{.mark}](#separazione-tra-motore-generico-e-caso-di-studio)
[]{.mark}

[[5.]{.mark} Progettazione e implementazione del Formal
Gate](#progettazione-e-implementazione-del-formal-gate)

[5.1 Ruolo architetturale e filosofia di
design](#ruolo-architetturale-e-filosofia-di-design)

[5.2 Meccanismo di filtering e bypass delle azioni
read-only[]{.mark}](#meccanismo-di-filtering-e-bypass-delle-azioni-read-only)
[]{.mark}

[[5.3 Integrazione con il framework di enforcement via MCP
Client]{.mark}](#integrazione-con-il-framework-di-enforcement-via-mcp-client)
[]{.mark}

[[5.4 Algoritmo di runtime enforcement e politiche di
sicurezza]{.mark}](#algoritmo-di-runtime-enforcement-e-politiche-di-sicurezza)
[]{.mark}

[[5.5 Preview su gemello e commit con
conferma]{.mark}](#preview-su-gemello-e-commit-con-conferma) []{.mark}

[5.6 Politiche di coordinamento e protocollo
PGA](#politiche-di-coordinamento-e-protocollo-pga)

[[6.]{.mark} Caso di studio e validazione
sperimentale](#caso-di-studio-e-validazione-sperimentale)

[6.1 Sistema pillbox[]{.mark}](#sistema-pillbox) []{.mark}

[6.2 Modelli ASM e binding[]{.mark}](#modelli-asm-e-binding) []{.mark}

[6.3 Scenari sperimentali[]{.mark}](#scenari-sperimentali) []{.mark}

[[6.4 Scelta del modello
linguistico]{.mark}](#scelta-del-modello-linguistico) []{.mark}

[6.5 Risultati[]{.mark}](#risultati) []{.mark}

[7. Conclusioni e sviluppi futuri](#conclusioni-e-sviluppi-futuri)

[7.1 Conclusioni[]{.mark}](#conclusioni) []{.mark}

[7.2 Limiti e validità](#limiti-e-validità)

[7.3 Sviluppi futuri](#sviluppi-futuri)

[8. Bibliografia](#bibliografia)

[]{.mark}

# [ ]{.mark}1. Introduzione[]{.mark}

## [1.1 Problema affrontato]{.mark}

[]{.mark}La progettazione di applicazioni basate sull'intelligenza
artificiale si sta evolvendo verso le cosiddette "architetture
agentiche", ovvero sistemi in cui i modelli linguistici (LLM) cessano di
essere semplici interfacce conversazionali, diventando il nucleo di un
sistema in grado di utilizzare strumenti, pianificare azioni e gestire
il workflow. []{.mark}

Gli agenti basati su LLM che richiamano strumenti esterni possono però
causare danni irreversibili in quanto le loro azioni possono differire
dall'intento dell\'utente.[]{.mark}

A differenza del software tradizionale, in cui suite di test e contratti
definiscono il comportamento previsto, gli agenti LLM operano senza una
specifica in quanto non esiste modo di verificare le loro azioni prima
dell\'esecuzione.

Le misure di sicurezza esistenti si basano sulla valutazione a
posteriori, ma questo li rende inadatti a sistemi critici dove le
conseguenze di malfunzionamenti possono essere catastrofiche.[]{.mark}

[Un episodio emblematico della gravità di tali rischi è rappresentato
dal caso documentato della piattaforma di sviluppo AI Replit \[12\]:
durante una sessione di scrittura automatica del codice (vibe coding),
l\'agente AI ha eliminato l\'intero database di produzione dell\'azienda
ignorando le istruzioni esplicite dell\'utente. Senza un meccanismo di
verifica formale e preventivo interposto prima dell\'attuazione,
l\'agente non possiede criteri deterministici per valutare
l\'ammissibilità delle proprie azioni, giudicando il successo
esclusivamente in base al progresso apparente verso
l\'obiettivo.]{.mark}

## [1.2 Stato dell'arte]{.mark}

La letteratura recente ha risposto a questa criticità proponendo
l\'evoluzione dalle semplici interfacce conversazionali a paradigmi
agentici quali ReAct (Reasoning and Acting) \[2\], che alternano fasi di
ragionamento esplicito all\'invocazione di strumenti esterni.

Per strutturare ed eseguire tali flussi ciclici sono nati framework
dedicati basati su grafi \[4\] \[15\], quali LangChain, LangGraph e
AutoGen.

Sul fronte dell\'integrazione con l\'ambiente, l\'affermazione del Model
Context Protocol (MCP) ha consentito di standardizzare l\'interazione
tra agenti e strumenti esterni (Agent-to-Tool), sostituendo le
integrazioni ad hoc con interfacce fortemente tipizzate e disaccoppiate.

Ciononostante, la maggior parte delle architetture correnti continua a
delegare il controllo di sicurezza a prompt di sistema o a filtri privi
di fondamento logico-matematico. Gli approcci di runtime verification e
la ricerca sul ragionamento neuro-simbolico evidenziano quindi la
pressante necessità di intercettare le azioni candidate prima
dell\'esecuzione fisicamente reale, validandole rispetto a specifiche
formali esplicite. []{.mark}

[Le singole tecniche di intercettazione, correzione locale e
ripianificazione non sono di per sé nuove. Nel runtime enforcement
classico un enforcer può bloccare un\'operazione non sicura oppure
prescriverne una sostitutiva \[27\]; il framework RSE (Runtime Safety
Enforcement) \[18\] ha mostrato come modellare con Abstract State
Machines eseguibili sia la logica di enforcement sia il sistema
controllato. Nel contesto specifico degli agenti LLM, RefineAct \[3\]
verifica le azioni prima dell\'esecuzione rispetto a specifiche Prolog
derivate automaticamente, chiedendo revisioni o inserendo passi di
conferma; AgentSpec \[7\] offre regole di runtime configurabili che
consentono di bloccare un\'azione, sottoporla all\'utente, sostituirla
con un\'alternativa prescritta o richiedere un\'auto-valutazione
all\'LLM. Altri lavori ragionano su sequenze di azioni anziché sulla
singola chiamata: Agent-C \[22\] impone vincoli temporali su sequenze
generate da LLM tramite specifiche formali, ragionamento SMT e
generazione vincolata, mentre WikiPlanner \[23\] ricava vincoli
temporali da conoscenza di dominio, li compila in monitor LTLf e ripara
i piani multi-passo anche in scenari medici. Il ragionamento prospettico
basato su modello è inoltre consolidato nei sistemi autonomi, ad esempio
con il Dynamic Model Predictive Shielding nel reinforcement learning
\[24\], e lavori recenti come MAPER \[25\] e POLARIS \[26\] integrano il
ragionamento degli LLM all\'interno di architetture
auto-adattative.]{.mark}

[Rispetto a questi approcci, il presente lavoro affronta una questione
più circoscritta: un\'azione corretta localmente può essere sicura in
isolamento ma rendere non realizzabili o non sicure le azioni successive
del piano, mentre richiedere all\'LLM di ripianificare a ogni rifiuto è
costoso quando una correzione locale sarebbe sufficiente. Il contributo
specifico consiste quindi nel decidere se applicare una correzione
prescritta formalmente solo dopo averne simulato l\'effetto sulla parte
del piano non ancora eseguita.]{.mark}

## 1.3 Contesto tecnologico[]{.mark}

L'architettura proposta si sviluppa su due domini tecnologici, che
questo progetto intende far comunicare: da un lato l\'ecosistema
probabilistico dell\'intelligenza artificiale e degli agenti,
dall\'altro l\'ecosistema deterministico dei metodi formali.

### [1.3.1 Dominio probabilistico (Ecosistema AI)]{.mark}

[Caratterizzato dall\'impiego di modelli linguistici di grandi
dimensioni per la comprensione dell\'intento dell\'utente in linguaggio
naturale e per la formulazione di piani d\'azione. In questo dominio, la
flessibilità e l\'adattabilità dell\'LLM sono compensate dall\'assenza
di garanzie di correttezza. L\'orchestrazione del flusso decisionale
viene gestita mediante grafi a stati (LangGraph), mentre l\'accesso agli
strumenti avviene tramite protocolli standardizzati (MCP).]{.mark}

In questo ecosistema, ogni componente assume un ruolo specifico:

- LLM (Ragionamento e NLP): I modelli linguistici di grandi dimensioni
  (basati su reti neurali artificiali) sono macchine di previsione
  statistica addestrate per comprendere e generare linguaggio naturale.
  In questo contesto costituiscono il nucleo cognitivo, occupandosi di
  comprendere l\'input fornito dall\'utente e di pianificare la
  strategia per raggiungere l\'obiettivo.

- LangGraph (Orchestratore): È il framework incaricato di gestire il
  flusso di lavoro. Modella la logica di controllo tramite grafi,
  gestisce la memoria dello stato e orchestra i cicli di feedback
  necessari per la validazione.

- Model Context Protocol - MCP (Standard di Comunicazione): Agisce come
  un layer di astrazione universale. Traduce le funzionalità dei servizi
  esterni in un\'interfaccia standard, permettendo all\'agente di
  interagire con qualsiasi risorsa (database, API, simulatori) in modo
  trasparente e senza codice personalizzato per ogni integrazione.

- Tools (Esecutori): Sono i servizi esterni deterministici che eseguono
  i task tecnici. Rappresentano la componente \"non-AI\" del sistema,
  garantendo risultati rigorosi a fronte delle istruzioni ricevute
  dall\'agente.

La struttura dei sistemi agentici basati su MCP (Figura 1) riflette
appieno il principio di separazione delle responsabilità nel quale gli
Agenti AI (attraverso framework, in questo caso LangGraph) si occupano
del ragionamento e della pianificazione, mentre l'esecuzione delle
azioni è in capo a sistemi tradizionali e deterministici, ovvero i
tools. Questo livello di astrazione garantisce che la natura
probabilistica dell'LLM non interferisca con il rigore richiesto
dall'esecuzione dei task.

[]{.mark}

Figura 1: Architettura di MCP. Fonte:
<https://modelcontextprotocol.io/docs/getting-started/intro>

### [1.3.2 Dominio deterministico (metodi formali e ASMETA)]{.mark}

Le Abstract State Machines (ASM) sono un metodo formale basato sulla
matematica per la specifica e la verifica di sistemi complessi. A
differenza degli LLM che sono probabilistici, le ASM sono rigorosamente
deterministiche: partendo da uno stato iniziale e applicando regole in
base a determinati input, la macchina transita verso uno stato
successivo calcolabile e prevedibile.

Per rendere le ASM utilizzabili a livello pratico, è stato sviluppato il
framework ASMETA (Abstract State Machine mETAmodeling), un set di
strumenti open source per la scrittura, validazione e simulazione di
modelli ASM.

All\'interno di questo ecosistema è presente AsmetaS (ASMETA Simulator),
ovvero il motore di simulazione vero e proprio. AsmetaS è capace di
eseguire a run-time il modello matematico, valutando le regole,
calcolando gli stati passo dopo passo e bloccando qualsiasi transizione
non valida rispetto alle regole formali scritte nel modello
\[1\].[]{.mark}

[Il simulatore può essere esposto come servizio tramite API REST
(AsmetaS\\@run.time), modalità con cui i modelli ASM vengono eseguiti a
runtime all\'interno del framework di enforcement \[21\].]{.mark}

Nell'ambito di questo progetto AsmetaS rappresenta lo strumento (non-AI)
a cui è assegnato il ruolo di "safety guard", ovvero di validazione di
conformità e di sicurezza. Intercettando i comandi strutturati generati
dall\'LLM prima della loro effettiva attuazione, il simulatore valuta la
legittimità della transizione, garantendo che nessuna allucinazione o
deviazione del modello linguistico violi i vincoli formali imposti.

## [1.4 Soluzione proposta]{.mark}

Per coniugare la flessibilità espressiva degli LLM con le garanzie
deterministiche dei metodi formali, il presente lavoro di tesi propone
un design pattern architetturale basato sul paradigma Proposer-Verifier
per la I/O sanitization e il runtime enforcement delle azioni degli
agenti sfruttando un agentic framework integrato con lo standard di
interoperabilità Model Context Protocol (MCP).

Il caso di studio consiste nell'ingegnerizzazione di un pattern per
l\'interazione tra un modello probabilistico (LLM) e un sistema di
verifica formale deterministico, rappresentato dal simulatore ad
Abstract State Machines AsmetaS \[1\]. Nel sistema proposto esso viene
interposto attivamente tra la fase decisionale e l\'attuazione materiale
sull\'ambiente: le azioni proposte dall\'agente linguistico vengono
intercettate a runtime e sottoposte alla verifica di precondizioni,
guardie e invarianti di sicurezza, abilitando l\'esecuzione solo in
presenza di un verdetto formale positivo e guidando cicli controllati di
auto-correzione in caso di violazione.[]{.mark}

[L\'implementazione del pattern, comprensiva del motore di
orchestrazione, del framework di enforcement e del caso di studio, è
contenuta in un repository GitHub \[17\].]{.mark}

# 2. Nozioni di background

## 2.1 Paradigma ReAct

L'evoluzione degli LLM sta cambiando il modo in cui questi vengono
utilizzati, passando da interfacce conversazionali ad agenti autonomi
che pianificano ed eseguono compiti complessi. In questo contesto
nascono paradigmi come ReAct (Reasoning and Acting) \[2\], che spingono
il modello a formulare un pensiero logico e una pianificazione prima di
invocare uno strumento esterno (Figura 2). I framework basati sui grafi
rappresentano l'ideale per la modellazione di questi processi,
permettendo la gestione della memoria, la persistenza dello stato e la
creazione di flussi ciclici e non lineari \[4\] \[15\].

Figura 2: Il paradigma ReAct. Fonte:
<https://research.google/blog/react-synergizing-reasoning-and-acting-in-language-models/>

Tuttavia, tutta questa autonomia espone il sistema a criticità
significative sul piano della sicurezza e dell\'affidabilità. A
differenza del software tradizionale, in cui il comportamento atteso è
disciplinato da contratti e suite di test, gli agenti basati su LLM
operano tipicamente in assenza di una specifica formale esplicita contro
cui validare le azioni prima della loro emissione. L\'affidamento a
vincoli di sicurezza codificati unicamente in linguaggio naturale
all\'interno del prompt (prompt-level constraints) si rivela inadeguato
nei contesti critici: tali direttive influenzano la distribuzione
probabilistica del testo generato ma non offrono alcuna garanzia
deterministica, portando i modelli a ignorare restrizioni esplicite ed
eseguire operazioni distruttive o irreversibili sull\'ambiente esterno.

La ricerca evidenzia quindi la necessità di introdurre una verifica
runtime basata sull'intercettazione delle azioni candidate proposte
dall\'agente prima che raggiungano i tool esecutivi, verificando il
soddisfacimento di pre condizioni e vincoli di conformità tramite motori
logici e restituendo feedback correttivi per guidare l\'agente verso
un\'auto-correzione sicura \[3\].

## 2.2 Framework agentici

L\'applicazione del paradigma ReAct è oggi facilitata dalla presenza di
framework dedicati allo sviluppo agentico e alla costruzione di
architetture complesse. All\'interno di questo ecosistema, l\'ambiente
open source LangChain e, in particolare, il framework di orchestrazione
basato su grafi LangGraph rappresentano uno standard consolidato. Mentre
LangChain si concentra principalmente sull\'astrazione e integrazione
dei componenti LLM, LangGraph introduce un runtime dedicato alla
gestione di workflow ciclici guidati da stati espliciti e transizioni
condizionali. Questi strumenti hanno preso particolarmente piede grazie
al loro approccio open source, tuttavia anche le grandi aziende del
settore hanno commercializzato le loro alternative. Degna di nota la
piattaforma AutoGen, sviluppata da Microsoft, che si concentra su
architetture multi-agente in cui diverse entità AI collaborano,
conversano e agiscono per risolvere task complessi, supportando
nativamente l\'esecuzione di codice e cicli di feedback strutturati
\[4\].

## 2.3 Protocolli di interconnessione

Il panorama dei framework agentici presenta principalmente due
dimensioni di interconnessione \[5\]:

- Comunicazione Verticale (Agent-to-Tool / MCP): disciplina
  l\'interazione tra l\'agente e le sue estensioni operative.
  Storicamente, l\'eterogeneità delle interfacce esterne imponeva lo
  sviluppo di wrapper proprietari, determinando un forte accoppiamento.
  Standard come il Model Context Protocol (MCP) consentono di esporre
  primitive deterministiche, API e strumenti esterni in modo
  disaccoppiato e guidato da schemi rigorosi. L\'architettura definita
  da MCP si articola su tre componenti fondamentali: l\'MCP Host
  (l\'applicazione dove l\'agente è in esecuzione), l\'MCP Client (il
  connettore incaricato di negoziare la connessione con i servizi) e
  l\'MCP Server (il fornitore di primitive) \[8\].

- Comunicazione Orizzontale (Agent-to-Agent / A2A): regola la
  cooperazione tra entità autonome (che possono essere basate su LLM o
  costituite da agenti deterministici e simbolici) attraverso protocolli
  strutturati (es. JSON-RPC via HTTP). Secondo lo standard A2A le
  specifiche di questi agenti sono definite tramite Agent Card, un
  artefatto formale che dichiara l\'identità, le capacità, i formati di
  input/output e le interfacce di invocazione dell\'agente.

## 2.4 Valutazione e sicurezza degli agenti

Le sfide relative al testing e alla standardizzazione di ambienti
agentici complessi non sono trascurabili. Progetti di ricerca come
ToolEMU introducono sandbox emulate tramite LLM per testare
l\'esecuzione di tool esterni da parte degli agenti e valutarne i rischi
\[6\]. Sul fronte della sicurezza a runtime è stato invece proposto
AgentSpec \[7\], un linguaggio specifico di dominio con cui l'utente
definisce regole di enforcement per agenti LLM: ogni regola associa un
evento che la attiva (ad esempio l'invocazione di un tool), un insieme
di predicati da verificare sullo stato e un'azione di enforcement da
applicare quando i predicati sono soddisfatti, come bloccare l'azione,
sottoporla all'ispezione dell'utente, eseguire un'azione correttiva
prescritta o richiedere all'LLM di rivalutare la propria scelta.

La maggiore autonomia che hanno assunto gli agenti ha portato ad
incidenti nel mondo reale, tra cui il già citato caso di Replit. Senza
una specifica che codifichi cosa significhi effettivamente \"successo\"
(inclusi i vincoli che devono essere rispettati durante l\'esecuzione),
l\'agente non ha alcuna base per l\'autovalutazione. Può giudicare le
proprie azioni solo in base al fatto che sembrino fare progressi verso
l\'obiettivo, non in base al rispetto dei limiti a cui l\'utente è
effettivamente interessato. Questo episodio mette in risalto la
necessità di soluzioni che siano in grado di valutare e porre delle
barriere alle azioni che questi framework agentici possono eseguire.

## 2.5 LLM Symbolic Reasoning

Negli ultimi anni la ricerca ha iniziato ad utilizzare approcci
neuro-simbolici per superare la mancanza di affidabilità deduttiva degli
LLM. Nasce così il Symbolic Reasoning, ovvero l'approccio con il quale
si mira a far collaborare modelli linguistici con motori matematici,
unendo l'elaborazione del linguaggio naturale (NLP) con il rigore
formale delle macchine.

In questo specifico ambito, la ricerca sta muovendo i primi passi
nell'integrazione di LLM all'interno del framework ASMETA, per assistere
l'utente nella traduzione di requisiti dal linguaggio
colloquiale.Tuttavia, l\'attuale letteratura si concentra su
integrazioni custom o specificamente addestrate. L\'utilizzo di
framework architetturali a grafo (come LangGraph) combinati a protocolli
di standardizzazione universale (come MCP) per orchestrare la
comunicazione tra l\'agente AI e il motore formale (AsmetaS),
rappresenta un\'area applicativa ancora inesplorata \[8\] \[9\] \[10\].

In questo contesto il modello ad Abstract State Machine diviene un
controllore attivo di I/O sanitization che presidia le comunicazioni,
intercettando ogni singola proposta di transizione e assicurando
l\'inviolabilità degli invarianti di sistema prima di abilitare
l\'attuazione fisica.

## 2.6 Feedback Loop e limiti all'auto-correzione

Indagini sull\'uso di feedback loop per la generazione guidata di codice
hanno dimostrato che restituire all\'agente gli errori e gli avvisi
sollevati da un sistema di validazione esterno permette al modello di
correggere e migliorare iterativamente il proprio output.

Tuttavia, la letteratura evidenzia anche una criticità in questo
processo: è stato osservato che, per ogni iterazione del ciclo,
l\'efficacia dell\'autocorrezione diminuisce in modo esponenziale, fino
a raggiungere un punto in cui ulteriori tentativi diventano del tutto
inefficaci.Per risolvere questa problematica, nel sistema proposto,
LangGraph non si limiterà a concatenare chiamate, ma fungerà da
orchestratore per il feedback loop tra l\'LLM e il motore formale.
Guiderà l\'autocorrezione e applicherà rigorose condizioni di uscita e
limiti di iterazione. Questo impedirà che il sistema continui a iterare
a vuoto una volta raggiunto il limite di inefficacia documentato dalla
ricerca \[11\].

## [2.7 Agent design pattern]{.mark} per la sicurezza[]{.mark}

[La progettazione di sistemi complessi basati su modelli linguistici ha
portato alla formalizzazione di specifici Agent Design Patterns volti a
sistematizzare la pianificazione, la cooperazione tra componenti e la
gestione dei vincoli operativi. Con riferimento al catalogo dei pattern
per agenti basati su Foundation Model codificato da Liu et al. \[16\],
l\'architettura sviluppata in questo lavoro si colloca all\'intersezione
di tre modelli principali: Multimodal Guardrails, Cross-Reflection e
Agent Adapter.]{.mark}

### [2.7.1 Multimodal Guardrails]{.mark}

[Il pattern Multimodal Guardrails \[16\] risponde alla necessità di
vincolare gli input e gli output dei modelli affinché rispettino
requisiti stringenti di sicurezza, robustezza e conformità a regole
predefinite. Nei contesti safety-critical, questo pattern prevede
l\'interposizione di un modulo di controllo o intercettore lungo il
canale di comunicazione tra l\'agente e l\'ambiente esterno.
Intercettando le proposte di azione prima della loro esecuzione fisica,
il guardrail ne valuta la conformità rispetto ai vincoli di sistema,
bloccando le transizioni non valide ed eventualmente applicando
politiche di shielding tramite l\'esecuzione di azioni di ripiego
sicure.]{.mark}

### [2.7.2 Cross-Reflection per il re-planning]{.mark}

[I pattern di Reflection \[16\] descrivono la capacità di un sistema di
raffinare e correggere un piano di azione sulla base di un feedback. La
tassonomia di riferimento distingue la Self-reflection (svolta
autonomamente dal modello stesso) dalla Cross-reflection, in cui la
valutazione e la formulazione del feedback provengono da un\'entità o da
un sistema di verifica esterno. In un contesto di verifica formale, lo
schema di Cross-reflection consente di tradurre la violazione di una
regola logica o di un\'invariante in un report di errore strutturato.
Questo feedback viene reiniettato nel contesto dell\'LLM per guidare un
ciclo di riesecuzione e ri-pianificazione (re-planning) mirato e
controllato.]{.mark}

### [2.7.3 Agent adapter per l'interoperabilità]{.mark}

[Il pattern Agent Adapter \[16\] definisce la presenza di interfacce
d\'astrazione standardizzate volte a connettere l\'agente con strumenti
ed estensioni esterne, garantendo interoperabilità, disaccoppiamento e
manutenibilità del codice. Nell\'architettura realizzata, questo pattern
trova piena attuazione nell\'adozione del Model Context Protocol (MCP).
MCP agisce da adapter standardizzato, consentendo all\'ambiente di
esecuzione dell\'agente (LangGraph) di dialogare in modo disaccoppiato
sia con il motore di verifica formale (AsmetaS) sia con i tool
dell\'ambiente simulato mediante primitive ed esposizioni di schemi
fortemente tipizzati.]{.mark}

## 2.8 Sistemi auto-adattativi e ciclo MAPE-K[]{.mark}

[Un sistema auto-adattativo è composto da un sistema gestito e da una
logica di adattamento che lo osserva e lo modifica a runtime. Il
riferimento architetturale più diffuso per questa logica è il ciclo
MAPE-K \[19\], che separa quattro attività (Monitor, Analyze, Plan,
Execute) operanti su una base di conoscenza condivisa (Knowledge): il
sistema viene osservato, lo stato osservato viene analizzato rispetto ai
requisiti, si pianifica un intervento e lo si attua.]{.mark}

[Il runtime enforcement si presta naturalmente a questa struttura: il
monitoraggio intercetta le azioni e osserva lo stato del sistema,
l\'analisi verifica le proprietà di sicurezza, la pianificazione calcola
un\'eventuale correzione e l\'esecuzione la applica. Il framework RSE
\[18\] segue questo schema, usando modelli ASM eseguiti a runtime come
conoscenza del ciclo.]{.mark}

[Quando più obiettivi di adattamento devono convivere, Weyns et al.
\[20\] descrivono il pattern Hierarchical Control, in cui cicli di
controllo di livello inferiore gestiscono obiettivi specifici, mentre
cicli di livello superiore ragionano su aspetti via via più ampi del
sistema. Nell\'architettura proposta questo pattern si concretizza in
due livelli: il ciclo inferiore è il framework di enforcement, che
preserva i vincoli di sicurezza, mentre il ciclo superiore è l\'agente
LLM, che persegue gli obiettivi dell\'utente (sezione 4.1).]{.mark}

# 3. Idea Progettuale

## 3.1 Obiettivi

### 3.1.1 Runtime Enforcement e I/O Sanitization

Gli LLM sono per loro natura probabilistici e vulnerabili ad
allucinazioni, faticano nel mantenere coerenza logica in sistemi
complessi basati su regole, tendendo a \"inventare\" passaggi.
L\'obiettivo è delegare all\'engine ASM il calcolo degli stati e la
validazione delle regole. In questo modo L\'LLM non deve dedurre lo
stato successivo, ma formula proposte di azione la cui conformità viene
certificata prima dell\'effettiva attuazione.

### 3.1.2 Gestione dello stato e controllo deterministico del flusso

Abbandonare l\'affidamento cieco al prompt engineering a favore di un
modello a grafo ciclico gestito tramite LangGraph. L\'obiettivo è
definire una macchina a stati condivisa (StateGraph) \[13\] in cui il
flusso di controllo è regolato da edge condizionali deterministici:
[]{.mark}

- [Se i modelli ASM approvano la transizione, l\'azione (originale o
  corretta) viene eseguita sul sistema e il grafo riporta l\'esito al
  nodo di pianificazione, che prosegue con il resto del piano.]{.mark}

<!-- -->

- Se viene rilevata la violazione di una guardia, l\'edge condizionale
  impedisce l\'esecuzione e devia il flusso verso il nodo di
  pianificazione, innescando un ciclo di retroazione.

### 3.1.3 Costruire un\'infrastruttura modulare

Invece di scrivere codice custom che lega indissolubilmente un LLM
specifico al web service AsmetaS, si strutturerà il sistema secondo le
più recenti raccomandazioni sull\'ingegneria del software agentico
\[14\].

A tal fine, il sistema si focalizza sulla comunicazione verticale
(Agent-to-Tool) attraverso l\'adozione dello standard Model Context
Protocol (MCP). Il motore formale AsmetaS, insieme al framework di
enforcement che ne orchestra i modelli, viene incapsulato all\'interno
di un server MCP che ne espone le primitive di simulazione e validazione
sotto forma di strumenti fortemente tipizzati. In questo modo, il
simulatore matematico risulta accessibile in modo agnostico rispetto al
modello linguistico e al framework di orchestrazione sottostante \[8\].

[Sebbene la letteratura analizzi anche lo standard A2A (Agent-to-Agent)
per la federazione di agenti autonomi eterogenei]{.mark} \[5\][, la sua
adozione è stata esclusa dall\'architettura di questo progetto. I
componenti del sistema non agiscono infatti come un agente autonomo
dotato di obiettivi propri con cui negoziare compiti, bensì come una
guardia deterministica e sincrona. Modellare l\'engine formale come un
semplice MCP Server consente all\'orchestratore LangGraph (MCP Host) di
invocare la sanitizzazione delle azioni con una latenza minima e una
struttura snella, evitando l\'overhead informatico e la complessità di
gestione di contratti di rete A2A.]{.mark}

### 3.1.4 Accessibilità naturale a metodi formali

La comprensione e l'utilizzo delle Abstract State Machines non sono
immediati, necessitano di esperienza nel campo della logica formale e
una solida padronanza della teoria dei linguaggi di specifica. Definire
formalmente stati, domini e regole di transizione impone una curva di
apprendimento ripida, che ha limitato l\'adozione di questi strumenti a
contesti di nicchia o ad ambienti prettamente accademici. L'integrazione
di un LLM consentirebbe a operatori non specialisti di interagire con un
modello matematico complesso attraverso il linguaggio naturale. L\'LLM
traduce le richieste colloquiali dell\'utente in chiamate strutturate e
decodifica gli stati restituiti dal simulatore matematico in spiegazioni
chiare e comprensibili, mantenendo inalterato il rigore scientifico del
modello sottostante.

## 3.2 Piano d'azione

### 3.2.1 Containerizzazione e validazione dell\'infrastruttura di base

La prima fase del progetto è dedicata all\'allestimento di un ambiente
di sviluppo isolato e riproducibile attraverso Docker:

- Creazione di immagini e container con supporto a sessioni CLI
  interattive per ospitare il runtime Python, LangGraph e i connettori
  verso il modello (Google Gemini via API).

- Verifica preliminare del canale di comunicazione MCP partendo da tool
  prototipali di test per poi validare l\'integrazione di server MCP
  operanti su API REST esterne. Questa fase garantisce la corretta
  gestione del protocolli e il recupero dinamico degli schemi da parte
  dell\'MCP Client.

### 3.2.2 Implementazione del server MCP

La seconda fase prevede il wrapping del motore formale:[]{.mark}

- [Implementazione del framework di enforcement: sviluppo in Python di
  un framework, esterno a LangGraph, che orchestra più sessioni di
  modelli ASM sul web service REST preesistente di AsmetaS (avvio delle
  sessioni, esecuzione dei passi, collegamento degli output di un
  modello agli input di un altro, verifica della correlazione tra
  richiesta, comando e conferma). Le decisioni di sicurezza restano
  interamente nei modelli ASM.]{.mark}

- [Implementazione del Server MCP (Agent-to-Tool): sviluppo, per il caso
  di studio, di un server MCP che contiene il framework di enforcement
  ed espone all\'agente tre tool generici: get_system_state e
  get_plan_status, dichiarati di sola lettura, e submit_plan, unico tool
  in grado di modificare il sistema.]{.mark}

- [Definizione dello Schema Enforcement (Pydantic): modellazione del
  contratto di comunicazione tra il Formal Gate e il server MCP tramite
  classi Pydantic (Plan e Action). Questo assicura che i piani proposti
  dall\'agente rispettino tassativamente la struttura attesa prima di
  raggiungere i modelli ASM, e che le risposte appartengano alla
  tassonomia delle decisioni (ALLOW, REPLACE, REPLAN, BLOCK).]{.mark}

### 3.2.3 Design dei prompt e logica di traduzione neuro-simbolica

Sarà necessario istruire l'agente proponente tramite prompt per il suo
ruolo di "traduttore" dell'intento espresso in linguaggio colloquiale
dall'utente in una proposta formale per l'ASM. Dovrà essere in grado di
mappare le richieste fornite dall'utente trasformandole in requisiti
tecnici validi da passare al motore formale e di interpretare l'output
dello stesso per renderlo comprensibile all'utente.

### 3.2.4 Sviluppo del grafo LangGraph

La fase conclusiva realizza il nucleo architetturale del progetto,
implementando un grafo ciclico a stati (StateGraph) retto da vincoli
rigidi e non scavalcabili dal prompt:

- Nodo Proponente (LLM): Elabora la richiesta utente e scrive l\'azione
  candidata nello stato del grafo, privo di accesso diretto agli
  attuatori reali.

Nodo Cancello Formale (Deterministic Gate): Funzione Python pura (senza
LLM) che intercetta la proposta, la invia al server MCP del caso di
studio, che la verifica con i modelli ASM e la esegue, e registra nello
stato l\'esito della verifica formale.

- Archi condizionali in uscita dal gate:

  - In caso di approvazione, l'azione è già stata eseguita dal server
    dopo il verdetto degli ASM. Il flusso torna al nodo proponente, che
    riporta l'esito o prosegue con le azioni rimanenti del piano.

  - In caso di violazione, nessuna modifica raggiunge l'ambiente e viene
    reindirizzato lo stato verso il nodo proponente come feedback
    direttivo per guidare l'autocorrezione. Il grafo applica un
    contatore di passi per turno, in modo da evitare eventuali loop
    infiniti di richieste all'LLM: al superamento della soglia, il nodo
    proponente può solo formulare la risposta finale, riportando gli
    esiti reali e le azioni non eseguite.

# [4.]{.mark} Progettazione e implementazione

## [4.1 Architettura neuro-simbolica]{.mark}

Nelle applicazioni mission-critical (guida autonoma, robotica medica,
sistemi industriali), l\'attuazione diretta da parte di un LLM è
inaccettabile. Lo scopo di questa tesi è risolvere questa sfida
implementando un\'architettura neuro-simbolica:[]{.mark}

- Componente Neurale (Probabilistica): l\'LLM opera come "planner",
  comprendendo l\'utente e pianificando azioni.

- Componente Simbolica (Deterministica): il cancello formale intercetta
  ogni azione proposta prima dell\'esecuzione fisica e la sottopone alla
  verifica formale di una specifica ASM (Abstract State Machine) tramite
  il web service AsmetaS.

[Dal punto di vista dei sistemi auto-adattativi (sezione 2.8),
l\'architettura è un\'istanza del pattern Hierarchical Control a due
livelli \[20\]]{.mark}:[]{.mark}

- [Livello inferiore (enforcement): il framework di enforcement realizza
  un ciclo MAPE-K in cui il monitoraggio riceve il piano e legge lo
  stato del sistema live, l\'analisi e la pianificazione sono svolte dai
  modelli ASM (verifica dei vincoli, calcolo della correzione, preview
  sul gemello) e l\'esecuzione consiste nel commit del comando
  confermato. I modelli ASM caricati su AsmetaS costituiscono la
  conoscenza del ciclo.]{.mark}

- [Livello superiore (pianificazione orientata agli obiettivi):
  l\'agente LangGraph interpreta la richiesta dell\'utente, formula un
  piano e, in base alla decisione dell\'enforcement, prosegue con il
  piano, accetta la correzione oppure ripianifica.]{.mark}

[La separazione delle responsabilità è netta: l\'enforcement preserva i
vincoli di sicurezza modellati, mentre il raggiungimento degli obiettivi
dell\'utente resta compito del Planner. L\'agente non è mai autorizzato
a modificare i parametri di sicurezza del sistema: può soltanto proporre
azioni, che vengono comunque verificate.]{.mark}

## [4.2 Anatomia dei nodi LangGraph]{.mark}

[L\'applicazione modella il ciclo decisionale tramite uno StateGraph di
LangGraph, ovvero un tipo di grafo nel quale i nodi comunicano leggendo
e scrivendo uno stato comune \[15\], nel nostro caso chiamato
AgentState. I componenti del sistema e le loro relazioni sono illustrati
nel diagramma dei componenti in Figura 3.]{.mark}

### [4.2.1 PlannerNode]{.mark}

[Il PlannerNode rappresenta la componente neurale dell\'agente che
gestisce l\'interazione diretta con l\'operatore umano, garantisce la
continuità del contesto e formula le proposte d\'azione. La
determinazione del prompt di sistema non è codificata rigidamente, ma
viene generata dinamicamente dal nodo stesso attraverso il metodo
build_default_system_prompt(tools, hints) in modo che possa adattarsi al
sistema in cui viene utilizzato. Il prompt descrive il significato dei
marcatori con cui il Formal Gate comunica l\'esito della verifica e
aggiunge le eventuali istruzioni di dominio (planner_hints) fornite dal
caso di studio. Le azioni ammesse e il significato dei motivi di rifiuto
non compaiono nel prompt, ma arrivano dalla descrizione del tool
submit_plan e dai risultati del server.]{.mark}

[Il flusso in uscita dal nodo è regolato dalla funzione di instradamento
condizionale planner_router. Quest\'ultima ispeziona l\'output generato
dall\'LLM:]{.mark}

- [se il modello richiede l\'esecuzione di un\'azione tramite una
  tool_call, la richiesta viene indirizzata al FormalGateNode per la
  successiva fase di verifica;]{.mark}

- [se l\'output consiste in una risposta testuale diretta all\'utente,
  la conversazione conclude il turno corrente raggiungendo lo stato
  END.]{.mark}

### [4.2.2 FormalGateNode]{.mark}

[Il suo obiettivo è garantire, in modo deterministico, che ogni azione
proposta dall\'LLM che modifica il sistema venga verificata rispetto
alle proprietà di sicurezza espresse nei modelli ASM eseguiti su
AsmetaS, prima di raggiungere il sistema. La verifica vera e propria non
avviene nel nodo, ma nel server MCP del caso di studio, che contiene il
framework di enforcement.]{.mark}

[Un punto a cui si è data particolare attenzione durante progettazione
di questo nodo è la sua agnosticità rispetto al dominio applicativo,
poiché il codice non doveva contenere assunzioni o stringhe rigide
legate a uno specifico contesto: i tool vengono scoperti tramite MCP e
gli unici nomi noti al nodo sono quelli del contratto con il server
(submit_plan e get_system_state), definiti in un modulo condiviso
(contracts.py).]{.mark}

[Il nodo integra un meccanismo di bypass grazie al quale i tool che
il]{.mark} [server dichiara di sola lettura, tramite l\'annotazione MCP
readOnlyHint, vengono eseguiti direttamente senza validazione formale
(verdetto BYPASS). L\'unico tool attuativo ammesso è submit_plan, che
viene inoltrato al server per la verifica e l\'esecuzione; qualsiasi
altro tool viene bloccato e il turno termina con un errore.]{.mark}

[Il gate non reinterpreta le decisioni del server: la decisione finale
dell\'enforcer ASM diventa così com\'è il verdetto del gate:]{.mark}

- [ALLOW: l\'azione è stata eseguita esattamente come proposta;]{.mark}

- [REPLACE (shielding): l\'enforcer ASM ha sostituito l\'azione con la
  correzione ammissibile più vicina, eseguita solo dopo la verifica sul
  gemello del sistema; il Planner deve dichiarare all\'utente che
  l\'azione originale non è stata eseguita;]{.mark}

- [REPLAN: nessuna modifica è stata applicata e il motivo torna al
  Planner per ripianificare. Allo stesso verdetto conduce un piano
  rifiutato prima di raggiungere gli ASM per errori di schema o di
  binding;]{.mark}

- [BLOCK: nessuna modifica è stata applicata e il Planner può soltanto
  spiegare il motivo all\'utente, senza proporre altre azioni nel turno
  (final_answer_only).]{.mark}

[A queste quattro decisioni il gate aggiunge due esiti propri, che non
provengono dagli ASM:]{.mark}

- [BYPASS: è stato eseguito un tool di sola lettura;]{.mark}

- [ERROR: errore operativo (server irraggiungibile, decisione non
  riconosciuta, incoerenza nel protocollo), fine del turno senza azioni
  di ripiego, con l\'indicazione se il comando sia stato applicato, non
  applicato o se l\'esito sia sconosciuto.]{.mark}

### [4.2.3 Instradamento dopo il Formal Gate]{.mark}

[Verifica ed esecuzione avvengono entrambe nel server MCP del caso di
studio, che applica il comando sul sistema solo dopo il verdetto degli
ASM e ne attende la conferma. In questo modo nessun percorso del grafo
può raggiungere l\'ambiente con un\'azione non verificata.]{.mark}

[La funzione di instradamento gate_router riporta il controllo al
PlannerNode per i verdetti BYPASS, ALLOW, REPLACE, REPLAN e BLOCK, così
che l\'LLM possa leggere l\'esito, proseguire con le azioni rimanenti
del piano o formulare una spiegazione trasparente e comprensibile per
l\'operatore, esplicitando se l\'azione richiesta è stata eseguita senza
modifiche oppure se è stato necessario l\'intervento correttivo del gate
di sicurezza. Il verdetto ERROR termina invece il turno.]{.mark}

[Lo stato condiviso AgentState contiene la conversazione (messages), il
verdetto del gate (guard_verdict) con il relativo motivo
(guard_feedback), il contatore dei passi del turno (planner_steps) e
l\'indicatore final_answer_only. La conversazione resta in memoria per
tutta la sessione, mentre contatori e verdetto vengono azzerati a ogni
nuovo messaggio dell\'utente.]{.mark}

[]{.mark}

[]{.mark}

[Figura 3: Diagramma dei componenti. Realizzato con
[draw.io](https://app.diagrams.net).]{.mark}

[]{.mark}

## **4.3 Mappa dei protocolli e topologia di comunicazione[]{.mark}**

[L'architettura del sistema adotta una netta separazione tra i
componenti interni di orchestrazione (eseguiti in-process all\'interno
dello stesso ambiente di runtime) e i moduli esterni deterministici o di
interfaccia con l\'ambiente fisico (eseguiti come processi isolati
out-of-process):]{.mark}

- [Cloud-to-Host Layer (HTTPS/REST): Il nodo proponente (PlannerNode),
  basato sul modello di linguaggio Google Gemini (il modello specifico è
  indicato dalla variabile d\'ambiente GEMINI_MODEL, ad esempio
  gemini-3.5-flash-lite), comunica con le API cloud per la generazione
  del ragionamento e delle proposte d\'azione tramite chiamate
  HTTP/REST]{.mark}.[]{.mark}

- [In-Process Memory Layer (LangGraph): L\'orchestrazione tra il
  proponente, il Formal Gate e l\'esecutore avviene all\'interno
  dell\'host LangGraph tramite passaggio di stato in RAM
  (AgentState).]{.mark}

- [Agent-to-Tool / MCP Layer (stdio): La comunicazione verso il server
  MCP del caso di studio, che contiene il framework di enforcement,
  avviene tramite un sottoprocesso isolato basato sullo standard Model
  Context Protocol (MCP), garantendo il disaccoppiamento
  dell\'esecuzione e l\'isolamento dei processi. L\'agente mantiene con
  il server un\'unica sessione persistente per tutta la chat, poiché il
  server conserva in memoria lo stato del sistema e
  dell\'enforcement.]{.mark}

- [Backend Engine Layer (HTTP/REST): Il framework di enforcement,
  eseguito nel processo del server MCP, pilota più sessioni di modelli
  ASM tramite chiamate REST verso il web service AsmetaS sviluppato in
  Java/Spring Boot: carica i modelli, avvia le sessioni, esegue i passi
  e ne legge lo stato.]{.mark}

[Nel presente lavoro di tesi, invece di adottare integrazioni ad hoc,
l\'architettura incapsula il framework di enforcement, e con esso le
funzionalità del simulatore formale, all\'interno di un MCP Server
dedicato al caso di studio, articolando la comunicazione su tre livelli
fondamentali:]{.mark}

- [Livello di Trasporto (JSON-RPC 2.0 su stdio): garantisce il
  disaccoppiamento dei processi e l\'isolamento dei guasti (fault
  isolation). I server MCP operano come processi figli la cui
  comunicazione è veicolata tramite flussi standard di input/output. Un
  eventuale stallo o eccezione in un server esterno non compromette
  l\'integrità del processo principale di orchestrazione.]{.mark}

- [Livello applicativo e messaggistica (MCP): standardizza
  l\'esposizione e l\'invocazione delle capacità dell\'agente sotto
  forma di skills mediante i metodi standard del protocollo (tools/list
  e tools/call).]{.mark}

- [Livello di Governance e Schema Enforcement (Pydantic): la conformità
  della comunicazione è garantita a runtime da contratti definiti
  tramite Pydantic (Plan e Action). I modelli descrivono i parametri del
  tool submit_plan, vengono esposti all\'LLM come JSON Schema tramite
  MCP e sono riconvalidati dal server in ingresso. Un piano non conforme
  viene respinto prima di raggiungere i modelli ASM e il Formal Gate lo
  restituisce al Planner come feedback.]{.mark}

## 4.4 Ciclo di esecuzione e schema enforcement[]{.mark}

[L\'interazione tra l\'agente proponente e il verificatore formale segue
un flusso in tre fasi distinte:]{.mark}

- [Inizializzazione della Sessione e Discovery MCP: All\'avvio
  dell\'applicazione, l\'host carica la configurazione del caso di
  studio indicato dalla variabile d\'ambiente USE_CASE e avvia il
  relativo server MCP come sottoprocesso stdio. Prima di servire
  richieste, il server carica i modelli ASM su AsmetaS, avvia le
  sessioni e inizializza il gateway di enforcement. L\'host interroga
  quindi il server mediante la primitiva tools/list per verificare la
  presenza dello strumento submit_plan e dello strumento
  get_system_state, che deve essere dichiarato di sola lettura, e invoca
  quest\'ultimo come verifica di disponibilità. Se una qualsiasi di
  queste condizioni fallisce (AsmetaS non raggiungibile, modello non
  caricabile, tool mancanti, risposta non valida), il sistema segnala
  l\'errore e termina prima di mostrare il prompt all\'utente
  (fail-fast).]{.mark}

- [Intercettazione a Runtime: Quando l\'LLM all\'interno del PlannerNode
  formula una proposta d\'azione sotto forma di tool call, il ciclo di
  esecuzione devia la richiesta verso il FormalGateNode. Se il tool è di
  sola lettura viene eseguito direttamente; se è submit_plan, il gate lo
  invia in modo sincrono al server MCP, dove i modelli ASM valutano il
  piano e, in caso di esito positivo, il comando viene eseguito sul
  sistema.]{.mark}

- [Instradamento e Risoluzione: La decisione restituita dal server
  determina il percorso condizionale del grafo:]{.mark}

  - [Se la decisione è ALLOW o REPLACE: l\'azione, originale o corretta
    dall\'enforcer, è già stata eseguita e confermata dal sistema; il
    Planner riceve l\'esito e le eventuali azioni rimanenti del
    piano.]{.mark}

  - [Se la decisione è REPLAN o BLOCK: l\'esecuzione fisica viene
    impedita. Il motivo restituito dagli ASM, accompagnato da una
    spiegazione in linguaggio naturale, viene reiniettato nella memoria
    contestuale dell\'LLM per sollecitare una nuova pianificazione
    (REPLAN) o la sola risposta finale (BLOCK).]{.mark}

  - [In caso di errore operativo: il turno termina senza azioni di
    ripiego.]{.mark}

[La sola presenza di interfacce JSON-RPC via MCP non garantisce che i
messaggi scambiati con il server mantengano sempre i tipi e i campi
attesi. Per prevenire che piani malformati raggiungano i modelli ASM, il
contratto tra Formal Gate e server applica uno schema enforcement
rigoroso basato su modelli dati Pydantic, definiti nel modulo condiviso
contracts.py:]{.mark}

[class Action(BaseModel):]{.mark}

[ model_config = ConfigDict(extra=\"forbid\", strict=True)]{.mark}

[ kind: str]{.mark}

[ parameters: dict\[str, Any\]]{.mark}

[\
class Plan(BaseModel):]{.mark}

[model_config = ConfigDict(extra=\"forbid\", strict=True)]{.mark}

[request_id: str = Field(min_length=1, max_length=100)]{.mark}

[expected_version: int = Field(ge=0)]{.mark}

[actions: list\[Action\] = Field(min_length=1, max_length=32)]{.mark}

[goals: dict\[str, Any\] = Field(default_factory=dict)]{.mark}

[]{.mark}

[Le opzioni extra=\"forbid\" e strict=True rifiutano campi aggiunti
dall\'LLM e conversioni implicite di tipo. Dopo lo schema, il binding
del caso di studio verifica il tipo di azione e i valori dei parametri.
Le risposte del server hanno uno stato tra tre valori ammessi:
completed, quando gli ASM hanno restituito una decisione;
invalid_request, quando il piano è stato rifiutato da schema o binding
(il gate lo tratta come REPLAN); recovery_required, quando si è
verificato un errore operativo (il gate lo tratta come ERROR).]{.mark}

## 4.5 Framework di enforcement[]{.mark}

[Il framework di enforcement è il componente che orchestra i modelli ASM
sul web service AsmetaS. È esterno a LangGraph, gira nel processo del
server MCP del caso di studio e non contiene alcuna logica di dominio né
decisioni di sicurezza: Python avvia le sessioni, esegue i passi, passa
gli output di un modello come input di un altro e verifica la
correlazione tra richiesta, simulazione, comando e conferma.]{.mark}

[I moduli principali sono:]{.mark}

- [rest_client: client REST verso AsmetaS-web-service, in grado di
  gestire più sessioni contemporanee; chiude solo le sessioni che ha
  aperto e non ripete mai automaticamente le scritture;]{.mark}

- [asm_runtime: ciclo di vita delle sessioni e ricostruzione del gemello
  del sistema, rigiocando la storia degli input del modello
  live;]{.mark}

- [preview_orchestrator: simulazione della correzione e delle azioni
  residue del piano sul gemello, con invocazione del modello
  coordinatore dopo ogni passo;]{.mark}

- [gateway: flusso completo di una richiesta (enforcer, simulazione,
  commit sul sistema live, conferma);]{.mark}

- [deploy: caricamento dei modelli sul web service;]{.mark}

- [mcp_facade: esposizione dei tool MCP get_system_state,
  get_plan_status e submit_plan;]{.mark}

- [contracts: tipi condivisi, contratto con il Formal Gate e interfaccia
  ModelBinding;]{.mark}

- [bootstrap: punti di ingresso generici del caso di studio, cioè
  l\'avvio del server MCP e l\'esecutore di scenari senza LLM.]{.mark}

[Il confine con il dominio è l\'interfaccia ModelBinding, implementata
da ogni caso di studio. Il binding traduce richieste, comandi e
osservazioni da e verso le funzioni di input e output dei modelli ASM,
senza decidere nulla sulla sicurezza. Fornisce inoltre la descrizione,
destinata all\'LLM, delle azioni ammesse e dei loro parametri, che il
server aggiunge alla descrizione di submit_plan, e un glossario dei
codici di motivo restituiti dall\'enforcer, che il server allega al
risultato come spiegazione in linguaggio naturale.]{.mark}

## 4.6 Separazione tra motore generico e caso di studio[]{.mark}

[Il repository è diviso in quattro parti con responsabilità
distinte:]{.mark}

- [core: il motore di orchestrazione generico (grafo LangGraph, Planner,
  Formal Gate, interfaccia a riga di comando), privo di conoscenza di
  dominio;]{.mark}

- [enforcement: il framework di enforcement, anch\'esso privo di
  conoscenza di dominio;]{.mark}

- [use_cases: i casi di studio, ognuno con la propria configurazione, il
  proprio binding e il proprio server MCP;]{.mark}

- [resources: i modelli ASM e le librerie, unico luogo del repository in
  cui sono presenti file .asm.]{.mark}

[Tutto ciò che il motore deve sapere su un dominio è racchiuso nella
struttura UseCaseConfig, che definisce il comando di avvio del server
MCP, il numero massimo di passi per turno e le istruzioni di dominio
aggiunte al prompt del Planner. Il caso di studio attivo si seleziona
con la variabile d\'ambiente USE_CASE, obbligatoria e senza valore
predefinito. Per collegare un nuovo dominio è sufficiente aggiungere i
modelli in resources e creare una cartella in use_cases con il binding,
la configurazione di enforcement e il server MCP, senza modificare core
né enforcement.]{.mark}

[All\'avvio il server MCP carica sul web service i modelli elencati
nella configurazione del caso di studio. Se il servizio non ha sessioni
attive carica tutti i file, sostituendo quelli omonimi; altrimenti
carica solo quelli mancanti, per non sostituire modelli eventualmente in
uso. Al termine verifica che il servizio conservi tutti i file
richiesti, altrimenti l\'avvio fallisce.]{.mark}

# [5.]{.mark} Progettazione e implementazione del Formal Gate

## 5.1 Ruolo architetturale e filosofia di design

Il Formal Gate Node costituisce il cuore dell'architettura proposta,
agendo come guardia deterministica di sanitizzazione interposta tra la
componente neurale (Planner Node) e l'ambiente di esecuzione,
raggiungibile soltanto attraverso il server MCP del caso di
studio.[]{.mark}

[Il nodo è realizzato in Python, senza chiamate a modelli linguistici,
le sue regole sono fisse e il suo esito dipende unicamente dalla tool
call proposta dal Planner e dalla risposta del server MCP. Il nodo non
valuta di persona la sicurezza delle azioni: questa è decisa dai modelli
ASM, che il framework di enforcement esegue su AsmetaS nel processo
del]{.mark}

[server. Il compito del gate è garantire che ogni azione attuativa passi
da quella verifica e consegnare al Planner la decisione così com\'è,
insieme alle istruzioni per riportarla correttamente
all\'utente.]{.mark}

[La natura deterministica di un nodo così realizzato garantisce che il
controllo di sicurezza non sia soggetto alle interpretazioni e
fluttuazioni tipiche dei modelli di linguaggio.]{.mark}

[Nello specifico, la filosofia di design del Formal Gate si fonda su tre
principi guida fondamentali:]{.mark}

- [Inviolabilità preventiva: Nessuna azione generata dall\'LLM che
  comporti una modifica dello stato dell\'ambiente viene trasmessa agli
  attuatori senza prima aver ottenuto un verdetto formale di
  conformità.]{.mark}

- [Agnosticismo dal dominio applicativo: Il codice del gate non contiene
  regole cablate o assunzioni rigide legate a uno specifico scenario. Le
  variabili da monitorare, i parametri d\'azione e le regole di
  sicurezza vengono estratti e valutati dinamicamente rispetto alla
  specifica del modello ASM caricato sul server.]{.mark}

- [Rigore algoritmico e riproducibilità: A parità di proposta d\'azione
  e di risposta del server, il Formal Gate produce sempre il medesimo
  esito; poiché anche i modelli ASM sono deterministici, a parità di
  stato del sistema e di richiesta la decisione di sicurezza è
  riproducibile.]{.mark}

## 5.2 Meccanismo di filtering e bypass delle azioni read-only[]{.mark}

[Per evitare l\'overhead computazionale e lo spreco di risorse dovuto
alla verifica formale sincrona di operazioni prive di rischi viene
eseguita una ispezione preliminare della tool call proposta dal
Planner:]{.mark}

- [Azioni di sola lettura: Gli strumenti dedicati esclusivamente
  all\'osservazione dell\'ambiente, che il server MCP dichiara
  esplicitamente di sola lettura tramite l\'annotazione readOnlyHint
  (get_system_state e get_plan_status), scavalcano la verifica formale
  tramite un meccanismo di bypass immediato. Queste operazioni non
  modificano lo stato del sistema e vengono eseguite direttamente dal
  Formal Gate.]{.mark}

- [Azioni di modifica dello stato: Qualsiasi azione che comporti
  un\'alterazione dello stato del sistema deve passare per l\'unico tool
  attuativo, submit_plan, e viene sottoposta al ciclo di verifica
  formale via MCP. Qualsiasi altro tool viene bloccato.]{.mark}

[]{.mark}

[A differenza di un riconoscimento basato sul nome del tool (ad esempio
su prefissi come get\\ o suffissi come \\status), che un tool con un
nome fuorviante potrebbe aggirare, la classificazione si fonda su una
dichiarazione esplicita del server, e un tool privo dell\'annotazione è
trattato per default come potenzialmente pericoloso.]{.mark}

## [5.3 Integrazione con il framework di enforcement via MCP Client]{.mark}

[La verifica delle azioni avviene mediante l\'invocazione sincrona del
server MCP del caso di studio, che contiene il framework di enforcement
e, attraverso di esso, pilota il simulatore formale AsmetaS. Il Formal
Gate intercetta la tool call candidata e la inoltra al server invocando
lo strumento submit_plan.]{.mark}

[La richiesta contiene un piano (Plan) composto da:]{.mark}

- [un identificativo di richiesta (request_id), assegnato dal Formal
  Gate e non dall\'LLM;]{.mark}

- [la versione dello stato del sistema su cui il piano è stato formulato
  (expected_version), letta dal Planner con get_system_state;]{.mark}

- [la sequenza ordinata delle azioni (actions), ognuna con un tipo e i
  relativi parametri;]{.mark}

- [gli eventuali obiettivi espressi dall\'utente (goals), ad esempio
  l\'intervallo di disponibilità.]{.mark}

[Lo stato del sistema non viene dichiarato dall\'LLM: il server lo legge
direttamente dal modello ASM che rappresenta il sistema live. La
versione attesa serve a rilevare piani formulati su uno stato non più
attuale. Il server applica in ogni caso al più la prima azione del
piano, eventualmente corretta; le azioni successive servono a verificare
che il piano nel suo complesso resti sicuro. Per eseguirle, il Planner
rilegge lo stato e invia un nuovo piano con la versione aggiornata. Un
piano reinviato con lo stesso identificativo e lo stesso contenuto
restituisce il risultato già calcolato, senza un secondo commit.]{.mark}

[Il modello ASM che svolge il ruolo di enforcer valuta la richiesta
applicando le precondizioni e le guardie definite nella specifica e
decide se consentirla, correggerla, chiederne la ripianificazione o
bloccarla.]{.mark}

## [5.4 Algoritmo di runtime enforcement e politiche di sicurezza]{.mark}

[]{.mark}Il ciclo di esecuzione del Formal Gate e l\'instradamento
condizionale delle decisioni sono sintetizzati nel diagramma di workflow
illustrato in Figura 4.[]{.mark}

[]{.mark}

[Figura 4:]{.mark} Diagramma di workflow[. Realizzato con
[draw.io](https://app.diagrams.net).]{.mark}

[]{.mark}

[In base alla decisione restituita dai modelli ASM, il sistema applica
in modo deterministico una delle seguenti politiche di
sicurezza:]{.mark}

- [Politica di shielding (REPLACE): l\'enforcer intercetta l\'operazione
  non ammissibile e calcola la correzione ammissibile più vicina a
  quella richiesta. La correzione non viene eseguita subito: viene prima
  simulata, insieme alle azioni residue del piano, su un gemello isolato
  del sistema (sezione 5.5), e raggiunge il sistema reale solo se la
  simulazione non rileva conflitti e lo stato reale non è cambiato nel
  frattempo.]{.mark}

- [Politica di re-planning (REPLAN): l\'esecuzione dell\'azione non
  valida viene fisicamente impedita e nessuna modifica raggiunge il
  sistema. Il codice di motivo restituito dall\'enforcer, accompagnato
  dalla spiegazione fornita dal binding, viene reiniettato nello stato
  del grafo (AgentState) e reindirizzato al PlannerNode per generare una
  nuova proposta possibilmente valida.]{.mark}

- [Politica di blocco (BLOCK): la richiesta non è ammissibile in sé (ad
  esempio si riferisce a un elemento inesistente o contiene vincoli
  incoerenti). Nessuna modifica viene applicata e il Planner può
  soltanto spiegare il motivo all\'utente, senza proporre altre azioni
  nel turno.]{.mark}

- [Politica fail-closed: nel caso in cui si verifichino guasti
  infrastrutturali, come la perdita di connessione con il server
  AsmetaS, o incoerenze nel protocollo tra i modelli, il gateway entra
  in uno stato di recupero e rifiuta ogni ulteriore scrittura fino al
  riavvio del server MCP. Il Formal Gate termina il turno notificando
  l\'anomalia all\'utente e indicando se il comando sia stato applicato,
  non applicato o se l\'esito sia sconosciuto. Non viene eseguita alcuna
  azione di ripiego predefinita, poiché questa raggiungerebbe il sistema
  senza essere stata verificata.]{.mark}

## [5.5 Preview su gemello e commit con conferma]{.mark}

[Quando l\'enforcer propone una correzione, verificare la sola azione
corretta non basta: la correzione potrebbe rendere non sicure le azioni
successive del piano. Per questo il framework esegue una verifica
controfattuale, detta preview, su un gemello del sistema:]{.mark}

- [Ricostruzione del gemello: il web service non offre un\'operazione di
  copia di una sessione, quindi il gemello è una nuova sessione del
  modello del sistema, ricostruita rigiocando l\'intera storia degli
  input del sistema live. Prima di procedere si verifica che lo stato
  ricostruito coincida esattamente con quello reale.]{.mark}

- [Simulazione del piano: sul gemello vengono eseguite la correzione e,
  in sequenza, le azioni residue del piano. Dopo ogni passo, un modello
  ASM coordinatore ispeziona lo stato simulato e registra eventuali
  violazioni; al termine, considerando anche gli obiettivi dell\'utente,
  restituisce l\'esito COMPATIBLE, CONFLICT o UNKNOWN. Una violazione
  rilevata in uno stato intermedio resta registrata anche se lo stato
  finale è sicuro.]{.mark}

- [Decisione: l\'esito della preview viene passato all\'enforcer, che
  emette il comando solo con esito COMPATIBLE; altrimenti la decisione è
  REPLAN. Le sessioni del gemello e del coordinatore vengono chiuse e il
  sistema live non viene mai toccato durante la simulazione.]{.mark}

[Prima di inviare il comando al sistema live, il gateway verifica
in]{.mark} [Python che il comando abbia l\'identificativo e la versione
di base della richiesta, che coincida esattamente con l\'azione valutata
dai modelli (o con la correzione validata dalla preview) e che lo stato
live non sia cambiato rispetto all\'istante in cui è stato letto. Il
comando viene quindi applicato con un passo del modello live, che lo
conferma o lo rifiuta (ACK); l\'enforcer legge la conferma e produce la
decisione finale. Decisione finale e conferma del sistema devono
concordare: ogni discrepanza è trattata come errore operativo.]{.mark}

## 5.6 Politiche di coordinamento e protocollo PGA

[Quando l\'enforcer trova una correzione locale per un\'azione non
ammissibile, il framework deve decidere come coordinare la correzione
con il resto del piano dell\'agente. Si possono individuare tre
politiche, che condividono le stesse regole di sicurezza e lo stesso
framework di esecuzione e differiscono solo nella risposta a un\'azione
localmente non sicura:]{.mark}

- [Always-Replan (AR): rifiuta l\'azione e chiede un nuovo piano, senza
  applicare la correzione]{.mark};[]{.mark}

- [Local-First (LF): applica subito la correzione senza considerare le
  azioni successive, se queste vengono bloccate, ripianifica in
  seguito;]{.mark}

- [Preview-Based Goal-Aware (PGA): simula la correzione e il piano
  residuo su un gemello isolato del sistema e applica la correzione solo
  se la simulazione è compatibile, altrimenti richiede un nuovo
  piano.]{.mark}

[Applicate agli scenari del capitolo 6, le tre politiche si comportano
in modo diverso. Nello scenario M1, AR chiede un nuovo piano anche se la
correzione sarebbe stata accettabile, LF applica la correzione e PGA la
applica dopo la preview, pagando il costo della simulazione. Nello
scenario M2, AR ripianifica prima di qualsiasi modifica, LF applica la
prima correzione e può dover rimediare in seguito a un sistema già
modificato, mentre PGA rileva il conflitto in anticipo e chiede un nuovo
piano senza aver toccato il sistema. Il framework realizzato adotta la
politica PGA, descritta nelle sezioni precedenti; l\'ipotesi alla base è
che subordinare il commit di una correzione al suo effetto sul piano
residuo eviti modifiche premature senza dover sempre ricorrere alla
ripianificazione dell\'LLM.]{.mark}

[Il protocollo PGA si articola in tre passi. Quando l\'enforcer giudica
non ammissibile un\'azione del piano e prescrive una correzione locale,
il framework simula la correzione seguita dalle azioni residue del piano
su un gemello isolato del sistema, ottenuto rigiocando la storia degli
input del sistema live (sezione 5.5). Dopo ogni azione simulata, lo
stato del gemello viene confrontato con i vincoli di sicurezza e con i
vincoli sugli obiettivi dell\'utente rappresentati esplicitamente nei
modelli (nel caso di studio, available_from e latest_time). La preview
restituisce uno di tre esiti: COMPATIBLE se tutte le azioni simulate
sono state eseguite e i vincoli sono rispettati, CONFLICT se un vincolo
modellato viene violato, UNKNOWN se le evidenze disponibili non bastano
per decidere.]{.mark}

[La correzione viene applicata al sistema live solo se la preview è
COMPATIBLE e lo stato live non è cambiato nel frattempo; in caso
contrario il piano viene rifiutato e l\'agente deve ripianificare. Per
rendere verificabile questa condizione, il protocollo richiede
identificativi di correlazione tra richiesta, preview e commit,
un\'esecuzione che non duplichi i comandi e la versione aggiornata dello
stato. La preview adottata è di tipo stretto: non tenta ulteriori
correzioni delle azioni residue non ammissibili e qualsiasi violazione
la rende conflittuale. Infine, un esito compatibile non autorizza
l\'esecuzione incondizionata del resto del piano: ogni azione successiva
è a sua volta sottoposta a enforcement rispetto allo stato reale
del]{.mark} [sistema, come avviene nello scenario M2-C.]{.mark}

# [6.]{.mark} Caso di studio e validazione sperimentale

Il codice, i modelli ASM e gli scenari descritti in questo capitolo (M1,
M2-A, M2-B e M2-C) sono contenuti nel repository del progetto \[17\],
nelle cartelle use_cases/pillbox e resources. Gli scenari possono essere
rieseguiti senza LLM tramite l\'esecutore di scenari JSON descritto
nella sezione 6.3.

## 6.1 Sistema pillbox[]{.mark}

[Il caso di studio di riferimento è un portapillole (pillbox) simulato,
che gestisce gli orari di assunzione di più farmaci distribuiti in
scomparti. L\'utente chiede in linguaggio naturale di spostare una dose;
l\'agente traduce la richiesta in un piano e il framework la verifica
con i modelli ASM prima di modificare gli orari.]{.mark}

[Il caso di studio estende il sistema auto-adattativo Medicine Reminder
and Monitoring (MRM) presentato in \[18\], che combina un portapillole
intelligente, un\'applicazione di controllo remoto e le prescrizioni
mediche. Nel sistema originale l\'enforcer reagisce a eventi osservati
sul portapillole, come dosi saltate o assunte in ritardo, applicando
strategie correttive (riprogrammare la dose quando la distanza tra le
assunzioni lo consente, saltare una dose mancata che interferirebbe con
la successiva, evitare sovrapposizioni dopo un\'assunzione tardiva).
Nell\'estensione considerata in questa tesi il sistema non si limita più
a reagire su un calendario predefinito: un agente LLM riceve richieste
spontanee del paziente (ad esempio posticipare una dose perché sarà
fuori casa) e pianifica le azioni per soddisfarle, mentre i vincoli di
sicurezza restano verificati in modo indipendente. L\'agente non è mai
autorizzato a modificare prescrizioni, decidere dosaggi o inventare
ritardi ammissibili: può soltanto proporre riprogrammazioni.]{.mark}

[Le richieste dell\'utente rientrano in due categorie:]{.mark}

- [M1 (richiesta correggibile localmente): il paziente chiede di
  spostare una sola dose a un orario fuori dalla finestra ammessa o in
  conflitto con una dose vicina; l\'enforcer trova un orario alternativo
  che rispetta i vincoli e gli obiettivi espressi, e la correzione può
  essere applicata senza un nuovo ciclo di pianificazione;]{.mark}

- [M2 (richieste che interagiscono): il paziente chiede più spostamenti,
  e una correzione sicura per la prima azione può entrare in conflitto
  con le successive, rendendo necessaria la valutazione delle
  interferenze tra farmaci ed eventualmente una nuova
  pianificazione.]{.mark}

[Lo stato iniziale, uguale a ogni avvio, è il seguente:]{.mark}

  -----------------------------------------------------------------------------------
  [Scomparto]{.mark}      [Farmaco]{.mark}       [Dosi]{.mark}      [Orari]{.mark}
  ----------------------- ---------------------- ------------------ -----------------
  [compartment1]{.mark}   [fosamax]{.mark}       [\[360\]]{.mark}   [06:00]{.mark}

  [compartment2]{.mark}   [sumatriptan]{.mark}   [\[730,            [12:10,
                                                 1140\]]{.mark}     19:00]{.mark}
  -----------------------------------------------------------------------------------

[]{.mark}

[Gli orari sono espressi in minuti dalla mezzanotte (ad esempio 17:30 =
1050) e l\'ora di sistema iniziale è 350 (05:50). Tra due dosi di
sumatriptan devono trascorrere almeno 120 minuti, mentre tra farmaci
diversi e tra due dosi di fosamax ne servono almeno 360. La prima dose
di sumatriptan ha una finestra clinica tra le 16:00 e le 18:00
(960,1080).]{.mark}

## 6.2 Modelli ASM e binding[]{.mark}

[Il caso di studio usa cinque modelli ASM caricati da resources
all\'avvio. Il modello del portapillole è stato rinominato
pillboxDevice.asm perché il web service conteneva già un modello con il
nome originale:]{.mark}

- [scheduler.asm, l\'enforcer: valida la richiesta, cerca la correzione,
  chiede la preview, emette il comando e attende la conferma.
  Restituisce una decisione (ALLOW, REPLACE, REPLAN, BLOCK) e un codice
  di motivo;]{.mark}

- [PreviewCoordinator.asm: giudica il piano simulato sul gemello
  (COMPATIBLE, CONFLICT, UNKNOWN); viene avviato in una nuova sessione
  per ogni preview;]{.mark}

- [pillboxDevice.asm: il portapillole simulato, che applica i comandi e
  li conferma; ne esiste una sessione live per tutta la chat e una
  sessione gemella per ogni preview;]{.mark}

- [configurationMgr.asm: gestore della configurazione, aggiornato con lo
  stato live all\'avvio e dopo ogni commit;]{.mark}

- [knowledge.asm: dati di dominio (farmaci e interferenze), importato
  dagli altri modelli e privo di una sessione propria.]{.mark}

[Lo scheduler è una macchina a fasi (in attesa di richieste, in attesa
della preview, in attesa della conferma) che dialoga con il framework
esclusivamente attraverso funzioni monitorate (gli input) e funzioni di
output. Quando l\'orario richiesto non è ammissibile, cerca l\'orario
ammissibile più vicino con una scansione crescente della finestra
clinica, eseguita interamente all\'interno di un singolo passo ASM: a
parità di distanza viene scelto l\'orario più basso, quindi il risultato
è deterministico. Se nessun orario è ammissibile, la decisione è
REPLAN.]{.mark}

[I parametri clinici (ora di sistema, finestre cliniche, distanze minime
tra le dosi) sono contenuti nella configurazione di enforcement del caso
di studio e vengono considerati fidati: l\'LLM non può fornirli né
modificarli. Il binding del pillbox ammette un solo tipo di azione,
reschedule, con parametri compartment, dose_index e time, e come
obiettivi l\'orario da cui l\'utente è disponibile (available_from) e
l\'orario entro cui la dose deve essere assunta (latest_time). I codici
di motivo che lo scheduler può restituire sono NO_REASON,
INVALID_TARGET, STALE_STATE, INVALID_WINDOW, NO_LOCAL_REPAIR,
PREVIEW_CONFLICT_REASON, PREVIEW_UNAVAILABLE, REACTIVE_PRIORITY,
COMMIT_REJECTED e COMMIT_TIMEOUT; per ognuno il binding fornisce una
spiegazione per l\'LLM.]{.mark}

[Le istruzioni di dominio aggiunte al prompt del Planner si limitano a
descrivere il sistema e il formato degli orari: l\'utente conosce solo i
nomi dei farmaci, mentre scomparti e indici sono dettagli interni che
l\'agente non deve esporre.]{.mark}

## 6.3 Scenari sperimentali[]{.mark}

[Gli scenari riguardano il sumatriptan e condividono gli stessi
obiettivi: l\'utente è disponibile dalle 16:00 e deve assumere la prima
dose entro le 18:30, che il Planner traduce in available_from = 960 e
latest_time = 1110.]{.mark}

  --------------------------------------------------------------------------------
  [Scenario]{.mark}   [Richiesta]{.mark}   [Azioni]{.mark}   [Esito atteso]{.mark}
  ------------------- -------------------- ----------------- ---------------------
  [M1]{.mark}         [sposta il           [dose 0 →         [REPLACE a
                      sumatriptan delle    1050]{.mark}      1020]{.mark}
                      12:10 alle                             
                      17:30]{.mark}                          

  [M2-A]{.mark}       [come M1, poi quello [dose 0 → 1050,   [REPLAN
                      delle 19 alle        dose 1 →          (conflitto)]{.mark}
                      18:20]{.mark}        1100]{.mark}      

  [M2-B]{.mark}       [come M2-A, poi      [dose 0 → 1050,   [REPLAN (conflitto
                      riportalo alle       dose 1 → 1100,    intermedio)]{.mark}
                      19]{.mark}           dose 1 →          
                                           1140]{.mark}      

  [M2-C]{.mark}       [come M1, poi quello [dose 0 → 1050,   [REPLACE a 1020, poi
                      delle 19 alle        dose 1 →          ALLOW]{.mark}
                      19:20]{.mark}        1160]{.mark}      
  --------------------------------------------------------------------------------

[]{.mark}

[Gli stessi piani possono essere eseguiti senza LLM tramite un esecutore
di scenari JSON, ognuno su un portapillole nuovo. Questa modalità
permette esperimenti controllati sul solo framework di enforcement,
separando il comportamento dei modelli ASM da quello del modello
linguistico.]{.mark}

## [6.4 Scelta del modello linguistico]{.mark}

[Per il Planner è stato usato gemini-3.5-flash-lite, appartenente alla
famiglia Gemini di Google e raggiunto tramite API. La scelta di un
modello della fascia leggera è coerente con il principio del pattern: la
sicurezza non dipende dall\'affidabilità dell\'LLM, perché ogni azione
attuativa è comunque decisa dai modelli ASM. Un errore del Planner (un
parametro sbagliato, un piano malformato, una proposta non sicura) viene
respinto dallo schema Pydantic o dall\'enforcer e non raggiunge il
sistema; l\'LLM influisce quindi sulla qualità dell\'interazione, non
sulla correttezza dell\'esito. Per questo non serve il modello più
capace disponibile, mentre contano la bassa latenza, che si somma a ogni
passo del turno (lettura dello stato e invio del piano), e il costo
contenuto per chiamata.]{.mark}

[I requisiti effettivi sul modello sono due: supportare il function
calling, poiché il Planner riceve i tool soltanto da questo canale e non
dal prompt di sistema, e produrre argomenti conformi allo schema di
submit_plan. Entrambi sono verificati dalle prove della sezione
6.5.]{.mark}

[Il modello non è cablato nel codice: il nome è letto dalla variabile
d\'ambiente GEMINI_MODEL, obbligatoria e senza valore predefinito, e può
essere sostituito senza modificare il motore, in linea con
l\'indipendenza dal modello linguistico indicata nelle
conclusioni.]{.mark}

## 6.5 Risultati[]{.mark}

[Gli scenari sono stati eseguiti sia con l\'esecutore senza LLM sia in
chat, con il Planner basato su gemini-flash-lite-latest, ottenendo in
tutti i casi l\'esito atteso.]{.mark}

- [M1: l\'orario richiesto (1050) dista solo 90 minuti dalla dose delle
  19:00 (1140). Lo scheduler propone la correzione più vicina, 1020
  (17:00), la preview sul gemello risulta COMPATIBLE e il comando viene
  applicato e confermato. Il Formal Gate restituisce al planner la
  decisione REPLACE e il Planner spiega all\'utente che l\'orario
  richiesto è stato sostituito.]{.mark}

- [M2-A: la correzione 1020 sarebbe ammissibile da sola, ma sul gemello
  la seconda azione porta a \[1020, 1100\], con una distanza di 80
  minuti. Il coordinatore restituisce CONFLICT e la decisione è REPLAN
  con motivo PREVIEW_CONFLICT_REASON: sul sistema reale non viene
  scritto nulla e il Planner chiede all\'utente come procedere.]{.mark}

- [M2-B: lo stato finale \[1020, 1140\] sarebbe sicuro, ma quello
  intermedio \[1020, 1100\] non lo è. Il coordinatore mantiene
  registrata la violazione e il piano viene rifiutato senza modifiche,
  dimostrando che la verifica riguarda l\'intera sequenza e non solo lo
  stato finale. Il Planner mantiene le tre azioni nello stesso invio e
  spiega che applicarne solo una parte non soddisferebbe la richiesta.
  Con la formulazione \"riportalo alle 19:00\" il Planner ha invece
  riferito l\'ultima azione una volta alla prima dose e una volta alla
  seconda: il riferimento ambiguo produce piani diversi, ma ciascuno
  viene comunque verificato dagli ASM.]{.mark}

- [M2-C: la correzione 1020 e la seconda azione portano a \[1020,
  1160\], con 140 minuti di distanza: la preview è COMPATIBLE e viene
  eseguita la sola prima azione. Il Planner rilegge lo stato
  (versione 1) e invia la seconda azione, che è già ammissibile e viene
  eseguita senza preview (ALLOW). Il Planner omette i goals nel secondo
  invio, perché l'utente li aveva espressi solo per la prima
  azione.]{.mark}

[Altre prove in chat hanno verificato il comportamento in situazioni non
coperte dagli scenari:]{.mark}

- [la richiesta di spostare il fosamax alle 10:00 viene corretta alle
  06:10 (370), poiché tra farmaci diversi servono 360 minuti e la dose
  di sumatriptan è alle 12:10; dopo quella delle 19:00 non c\'è spazio
  per un orario più vicino. Il Planner omette i goals già al primo
  invio, e la richiesta si completa in un unico invio;]{.mark}

- [la richiesta di spostare il sumatriptan alle 17:30 senza indicare
  alcuna disponibilità produce lo stesso esito di M1 (REPLACE a
  1020);]{.mark}

- [Una richiesta non esprimibile con le azioni ammesse (saltare la prima
  dose di fosamax) non genera alcun invio: il Planner legge lo stato,
  spiega che il sistema consente solo di riprogrammare la dose a un
  nuovo orario e lascia il sistema invariato;]{.mark}

- [una finestra impossibile (disponibilità dalle 20:00 con scadenza alle
  15:00) produce BLOCK con motivo INVALID_WINDOW e il Planner si limita
  a spiegarne la ragione.]{.mark}

# 7. Conclusioni e sviluppi futuri

## 7.1 Conclusioni[]{.mark}

[Il lavoro ha realizzato un design pattern architetturale per il
runtime]{.mark} [enforcement delle azioni di agenti LLM, in cui la
componente neurale (il Planner) propone e la componente simbolica (i
modelli ASM eseguiti su AsmetaS) decide. Il Formal Gate, realizzato come
nodo deterministico del grafo LangGraph, garantisce che nessuna azione
non verificata raggiunga il sistema: solo i tool dichiarati di sola
lettura evitano la verifica, ogni modifica passa per un unico tool
attuativo e ogni errore termina il turno senza azioni di
ripiego.]{.mark}

[Le decisioni di sicurezza restano interamente nei modelli formali,
mentre Python si limita a orchestrarne le sessioni e a verificare la
correlazione tra richiesta, simulazione, comando e conferma. La verifica
controfattuale su un gemello del sistema estende lo shielding oltre la
singola azione, impedendo che una correzione renda non sicuro il resto
del piano. L\'adozione di MCP e la separazione tra motore generico,
framework di enforcement e casi di studio rendono infine l\'architettura
indipendente dal dominio e dal modello linguistico.]{.mark}

[Il caso di studio del portapillole ha mostrato che l\'agente traduce
correttamente le richieste in linguaggio naturale in piani verificabili
e spiega all\'utente gli interventi dell\'enforcer, e che il sistema
rifiuta piani che sarebbero sicuri nello stato finale ma non negli stati
intermedi.]{.mark}

## 7.2 Limiti e validità

[I principali limiti riguardano la fedeltà del modello usato come
gemello e la completezza dei vincoli modellati. Poiché la preview si
basa su un modello eseguibile, non può tenere conto di eventi ambientali
o comportamenti del sistema non modellati, e l\'esito compatibile vale
solo rispetto ai vincoli di sicurezza e agli obiettivi rappresentati
esplicitamente; nel caso di studio, ad esempio, gli obiettivi sono
limitati a vincoli temporali come l\'orario massimo di assunzione. La
strategia adottata è inoltre conservativa: qualsiasi violazione rilevata
durante la preview porta alla ripianificazione, anche quando un\'azione
successiva ripristinerebbe uno stato sicuro (scenario M2-B). Infine, una
preview compatibile non garantisce la sicurezza delle esecuzioni future,
che devono essere comunque verificate sullo stato reale del sistema. La
validazione sperimentale, condotta su un solo caso di studio e su un
numero limitato di scenari, ha carattere funzionale e non
quantitativo.]{.mark}

## 7.3 Sviluppi futuri

[Il lavoro si presta a diverse estensioni:]{.mark}

- [Costo della preview: occorre misurare il tempo di esecuzione e il
  numero di passi ASM aggiuntivi introdotti dalla preview al crescere
  della lunghezza del piano;]{.mark}

- [Preview meno conservativa: si potrebbero valutare politiche che
  tentano correzioni locali anche sulle azioni residue, o che
  distinguono violazioni transitorie accettabili da violazioni
  effettive, mantenendo garanzie formali;]{.mark}

- [Qualità della ripianificazione: valutare in modo sistematico, su un
  insieme più ampio di richieste e di modelli linguistici, se le
  richieste non strutturate vengono tradotte in piani adeguati e se il
  Planner riesce a trovare alternative valide a partire dal feedback
  formale;]{.mark}

- [Nuovi casi di studio: grazie alla separazione tra motore generico,
  framework di enforcement e casi di studio (sezione 4.6), il pattern
  può essere applicato ad altri domini safety-critical aggiungendo
  soltanto modelli ASM, binding e server MCP.]{.mark}

# 8. Bibliografia

\[1\] A. Gargantini, E. Riccobene, and P. Scandurra, "A metamodel-based
language and a simulation engine for abstract state machines," *J.
Univers. Comput. Sci*., vol. 14, no. 12, 2008.

\[2\] S. Yao, J. Zhao, D. Yu, N. Du, I. Shafran, K. Narasimhan, and Y.
Cao, "ReAct: Synergizing reasoning and acting in language models," in
*Proc. 11th Int. Conf. Learning Representations (ICLR)*, 2023.

\[3\] F. Batole, F. Khomh, and H. Rajan, "RefineAct: Automatic runtime
verification of LLM agent actions," in *Proc. 41st IEEE/ACM Int. Conf.
Automated Software Engineering (ASE)*, Munich, Germany, 2026.

\[4\] H. Derouiche, Z. Brahmi, and H. Mazeni, "Agentic AI frameworks:
Architectures, protocols, and design challenges," arXiv preprint
arXiv:2508.10146, 2025.

\[5\] K. Vaidhyanathan and H. Muccini, "Software architecture meets
agentic AI," tutorial at the *IEEE Int. Conf. Software Architecture
(ICSA 2026)*, 2026.

\[6\] Y. Ruan et al., "Identifying the risks of LM agents with an
LM-emulated sandbox," in *Proc. Int. Conf. Learning Representations
(ICLR)*, 2024.

\[7\] H. Wang, C. M. Poskitt, and J. Sun, "AgentSpec: Customizable
runtime enforcement for safe and reliable LLM agents," in *Proc. 48th
IEEE/ACM Int. Conf. Software Engineering (ICSE)*, 2026.

\[8\] A. Ehtesham et al., "A survey of agent interoperability protocols:
Model Context Protocol (MCP), Agent Communication Protocol (ACP),
Agent-to-Agent Protocol (A2A), and Agent Network Protocol (ANP)," arXiv
preprint arXiv:2505.02279, 2025.

\[9\] O. Sultan, E. Stern, and D. Shahaf, "A neuro-symbolic approach for
reliable proof generation with LLMs: A case study in Euclidean
geometry," arXiv preprint arXiv:2505.14479, 2025.

\[10\] A. Bombarda, S. Bonfanti, A. Gargantini, and N. Pellegrinelli,
"Formalizing and validating properties in Asmeta with large language
models," arXiv preprint arXiv:2603.15375, 2026.

\[11\] M. A. Palavalli and M. Santolucito, "Using a feedback loop for
LLM-based infrastructure as code generation," arXiv preprint
arXiv:2411.19043, 2024.

\[12\] M. Tyson, "AI coding platform goes rogue during code freeze and
deletes entire company database," *Tom's Hardware*, 2025. \[Online\].
Available:
<https://www.tomshardware.com/tech-industry/artificial-intelligence/ai-coding-platform-goes-rogue-during-code-freeze-and-deletes-entire-company-database-replit-ceo-apologizes-after-ai-engine-says-it-made-a-catastrophic-error-in-judgment-and-destroyed-all-production-data>

\[13\] F. Jabbarvaziri, "Remember, don't re-read: Stateful ReAct agents
for token-efficient autonomous experimentation," arXiv preprint
arXiv:2606.14945, 2026.

\[14\] A2A Protocol, "A2A and MCP," 2026. \[Online\]. Available:
<https://a2a-protocol.org/latest/topics/a2a-and-mcp/#a2a-mcp-complementary-protocols-for-agentic-systems>

\[15\] LangChain, "StateGraph," *LangChain Reference*, 2026. \[Online\].
Available:
<https://reference.langchain.com/python/langgraph/graph/state/StateGraph>

\[16\] Y. Liu et al., "Agent design pattern catalogue: A collection of
architectural patterns for foundation model based agents," arXiv
preprint arXiv:2405.10467, 2024.

\[17\] L. Gallizioli, "agentic-mcp-framework: runtime enforcement delle
azioni di agenti LLM mediante Abstract State Machines," GitHub
repository, 2026. \[Online\]. Available:
<https://github.com/gallizzz/agentic-mcp-framework>

\[18\] S. Bonfanti, E. Riccobene, and P. Scandurra, "A component
framework for the runtime enforcement of safety properties," *J. Syst.
Softw.*, vol. 198, p. 111605, 2023.

\[19\] J. O. Kephart and D. M. Chess, "The vision of autonomic
computing," *Computer*, vol. 36, no. 1, pp. 41--50, 2003.

\[20\] D. Weyns, B. Schmerl, V. Grassi, S. Malek, R. Mirandola, C.
Prehofer, J. Wuttke, J. Andersson, H. Giese, and K. M. Göschka, "On
patterns for decentralized control in self-adaptive systems," in
*Software Engineering for Self-Adaptive Systems II*. Berlin, Heidelberg:
Springer, 2013, pp. 76--107.

\[21\] A. Bombarda, S. Bonfanti, A. Gargantini, E. Riccobene, and P.
Scandurra, "ASMETA: A comprehensive tool set for formal system
engineering based on abstract state machines," *Sci. Comput. Program*.,
vol. 253, p. 103508, 2026.

\[22\] A. Kamath, S. Zhang, C. Xu, S. Ugare, G. Singh, and S.
Misailovic, "Enforcing temporal constraints for LLM agents," 2025,
\[Online\], Available: <https://arxiv.org/abs/2512.23738>

\[23\] B. Zhang, "WikiPlanner: Wiki-derived temporal monitors for safe
LLM agent planning -- a medical-domain proof of concept," *AI Agent*,
vol. 2, p. 25, 2026.

\[24\] A. Banerjee, K. Rahmani, J. Biswas, and I. Dillig, "Dynamic model
predictive shielding for provably safe reinforcement learning," in
*Advances in Neural Information Processing Systems*, vol. 37, 2024.

\[25\] P. Maia, L. Vieira, G. L. B. De Oliveira, M. Chagas, A. Bandeira,
and C. Rocha, "MAPER: Extending MAPE-K with LLM-based reasoning to
manage unanticipated situations in self-adaptive systems," in *Proc.
21st Int. Conf. Software Engineering for Adaptive and Self-Managing
Systems (SEAMS '26)*. ACM, 2026, pp. 239--250.

\[26\] D. Pandey, V. Gupta, P. Singhal, and K. Vaidhyanathan, "POLARIS:
Is multi-agentic reasoning the next wave in engineering self-adaptive
systems?," in *Proc. 21st Int. Conf. Software Engineering for Adaptive
and Self-Managing Systems (SEAMS 2026)*, Rio de Janeiro, Brazil. ACM,
2026, pp. 188--193.

\[27\] Y. Falcone, L. Mariani, A. Rollet, and S. Saha, "Runtime failure
prevention and reaction," in *Lectures on Runtime Verification*. Cham:
Springer, 2018, pp. 103--134.
