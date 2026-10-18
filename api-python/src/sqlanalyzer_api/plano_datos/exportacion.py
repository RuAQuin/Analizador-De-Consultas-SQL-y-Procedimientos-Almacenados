"""Paso 7 · Exportación con pg_dump del script completo (estructura + datos)."""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from ..config import ConfigPostgres

log = logging.getLogger(__name__)


class ErrorExportacion(RuntimeError):
    pass


def exportar(config: ConfigPostgres, nombre_bbdd: str) -> Path:
    """Ejecuta pg_dump en formato SQL plano y devuelve la ruta del fichero generado."""
    config.directorio_dumps.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = (config.directorio_dumps / f"{nombre_bbdd}_{marca}.sql").resolve()
    orden = [
        config.pg_dump,
        "--host", config.host,
        "--port", str(config.puerto),
        "--username", config.usuario,
        "--dbname", nombre_bbdd,
        "--format", "plain",
        "--encoding", "UTF8",
        "--no-owner",
        "--no-privileges",
        "--no-password",
        "--file", str(ruta),
    ]
    # La contraseña va por entorno, nunca en la línea de órdenes.
    entorno = {**os.environ, "PGPASSWORD": config.contrasena}
    try:
        proceso = subprocess.run(orden, env=entorno, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise ErrorExportacion(
            f"no se encuentra pg_dump ('{config.pg_dump}'); indica su ruta en la variable PG_DUMP"
        ) from None
    if proceso.returncode != 0:
        ruta.unlink(missing_ok=True)
        raise ErrorExportacion(f"pg_dump terminó con código {proceso.returncode}: {proceso.stderr.strip()}")
    log.info("Exportación guardada en %s", ruta)
    return ruta
