"""Pillbox use case: the enforcement gateway verifies and executes rescheduling plans."""

from pathlib import Path
import sys
from core.config import UseCaseConfig

USE_CASE_DIR = Path(__file__).resolve().parent

PLANNER_HINTS = """\
- Il sistema è un portapillole con due scomparti (dati sintetici): `compartment1` contiene fosamax, `compartment2` contiene sumatriptan.
- Gli orari sono minuti dalla mezzanotte (0-1439): ad esempio 17:30 = 1050, 19:00 = 1140. Gli indici delle dosi partono da 0.
- Prima di proporre una modifica leggi lo stato con `get_system_state`: ti servono la versione (`version`) e gli orari attuali.
- Per modificare lo schedule usa `submit_plan`; `submission` contiene SOLO questi quattro campi, senza aggiungerne altri:
  - `request_id`: una stringa qualsiasi, viene sostituita automaticamente;
  - `expected_version`: la versione appena letta;
  - `actions`: la lista ordinata delle azioni, ciascuna `{"kind": "reschedule", "parameters": {"compartment": ..., "dose_index": ..., "time": ...}}`;
  - `goals` (facoltativo): `{"available_from": ..., "latest_time": ...}`, cioè da quando il paziente è disponibile ed entro quando deve prendere la dose. Valgono SOLO per la prima azione della lista.
- Viene applicata al massimo la PRIMA azione, eventualmente corretta dall'enforcer; le altre servono solo a verificare il piano. Per le azioni successive rileggi lo stato e invia un nuovo `submit_plan` con la nuova versione, la lista delle azioni rimanenti e in `goals` solo i vincoli che l'utente ha dato per quella dose (se non ne ha dati, ometti `goals`).
- Non inventare mai separazioni minime tra dosi o finestre cliniche: le decide solo l'enforcer.
- Se un piano riceve `PREVIEW_CONFLICT_REASON`, il piano completo non è realizzabile: NON reinviarne solo una parte (ad esempio togliendo le azioni rimanenti) per far applicare la prima azione. Proponi all'utente un piano alternativo completo oppure chiedigli come procedere.
- Motivi che l'enforcer può restituire (non attribuirgli altri significati):
  - `NO_REASON`: nessun problema; con REPLACE l'orario richiesto non era ammesso ed è stato sostituito con quello applicato.
  - `STALE_STATE`: la versione inviata non è quella attuale, oppure lo stato è cambiato durante la verifica; rileggi lo stato e riprova.
  - `NO_LOCAL_REPAIR`: nessun orario ammesso rispetta insieme la richiesta e i `goals` inviati (disponibilità e scadenza).
  - `PREVIEW_CONFLICT_REASON`: la correzione sarebbe ammessa, ma il resto del piano porterebbe a un conflitto tra dosi.
  - `PREVIEW_UNAVAILABLE`: la simulazione del piano non ha dato un esito conclusivo.
  - `INVALID_WINDOW`: i vincoli indicati sono incoerenti (es. disponibilità dopo la scadenza).
  - `INVALID_TARGET`: la dose indicata non esiste o è già passata.
  - `COMMIT_REJECTED`: il portapillole ha rifiutato il comando.
  - `COMMIT_TIMEOUT`: il portapillole non ha confermato il comando in tempo.
  - `REACTIVE_PRIORITY`: un evento del portapillole (dose saltata o presa in ritardo) ha la precedenza; riprova dopo.
"""

USE_CASE = UseCaseConfig(
    environment_mcp_command=[sys.executable, str(USE_CASE_DIR / "mcp_server.py")],
    gate_mode="submit",
    submit_tool="submit_plan",
    submit_request_id_path="submission.request_id",
    health_tool="get_system_state",
    decision_mapping={
        "ALLOW": "APPROVED",
        "REPLACE": "SHIELDED",
        "REPLAN": "REPLAN",
        "BLOCK": "BLOCKED",
    },
    max_steps_per_turn=6,
    planner_hints=PLANNER_HINTS,
)
