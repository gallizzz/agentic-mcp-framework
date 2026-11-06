"""Uploads the ASM models and libraries listed by a use case to the ASMETA service.

Runs only at startup, before any session is opened. This is the single place where `.asm`
files leave the repository (`resources/`) and reach the service; graph nodes never do it.
"""

import logging
from pathlib import Path
from .contracts import AsmError
from .rest_client import AsmetaRestClient
logger = logging.getLogger(__name__)

def deploy(client: AsmetaRestClient, models: list[Path], libraries: list[Path],
           require_idle: bool = False) -> list[str]:
    """Makes the service hold the given sources; returns the uploaded file names.

    On an idle service every file is uploaded, replacing same-name files, so the
    service matches the local sources. With active sessions only missing files
    are uploaded, never replacing a model that may be in use.
    """
    if not models:
        raise AsmError("No ASM models to deploy")
    sources = models + libraries
    for path in sources:
        if not path.is_file():
            raise AsmError(f"ASM source not found: {path}")

    idle = not client.running_models()
    if require_idle and not idle:
        raise AsmError("Deployment requires a dedicated service with no active models")
    present = client.inventory()

    uploaded, kept = [], []
    for path in sources:
        if idle or path.name not in present:
            client.upload(path)
            uploaded.append(path.name)
        else:
            kept.append(path.name)
    if kept:
        logger.warning("Service busy: kept existing %s without replacing them; "
                       "they may differ from the local sources", ", ".join(kept))

    missing = {p.name for p in sources} - client.inventory()
    if missing:
        raise AsmError(f"The service did not retain: {', '.join(sorted(missing))}")
    return uploaded
