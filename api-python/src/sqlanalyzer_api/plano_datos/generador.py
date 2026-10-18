"""Generador de BBDD: encadena los ocho pasos del Módulo 1 del esquema funcional.

1. Especificación  2. Validación (pglast + FK)  3. Ordenación por FK
4. Creación de la BBDD y sus tablas  5. Inserción de datos (+ FK al final)
6. ANALYZE  7. Exportación con pg_dump  8. Registro en el repositorio de análisis

Si algo falla una vez creada la BBDD, se elimina para no dejarla a medias.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import ConfigPostgres
from . import ejecucion, exportacion, registro
from .ejecucion import TablaCargada
from .especificacion import EspecificacionBbdd
from .validacion import validar

log = logging.getLogger(__name__)


@dataclass
class ResultadoGeneracion:
    nombre: str
    conexion: str
    orden: list[str]
    tablas: list[TablaCargada]
    ruta_dump: Path | None = None
    id_registro: int | None = None
    segundos: float = 0.0
    script: str = field(default="", repr=False)


def generar_bbdd(espec: EspecificacionBbdd, config: ConfigPostgres, *,
                 reemplazar: bool = False, exportar: bool = True,
                 registrar: bool = True) -> ResultadoGeneracion:
    inicio = time.perf_counter()

    # Pasos 2 y 3: no se toca PostgreSQL hasta que todo es válido.
    validado = validar(espec)
    log.info("Especificación válida. Orden de creación: %s", " -> ".join(validado.orden))

    ejecucion.crear_bbdd(config, espec.nombre, reemplazar)
    log.info("BBDD '%s' creada", espec.nombre)
    ruta_dump: Path | None = None
    try:
        cargadas = ejecucion.crear_y_cargar_tablas(config, espec, validado)
        ejecucion.analizar(config, espec.nombre, validado.orden)
        if exportar:
            ruta_dump = exportacion.exportar(config, espec.nombre)
        id_registro = registro.registrar(config, espec, cargadas, ruta_dump) if registrar else None
    except BaseException:
        log.error("Fallo generando '%s': se elimina la BBDD a medio crear", espec.nombre)
        if ruta_dump:
            ruta_dump.unlink(missing_ok=True)
        ejecucion.eliminar_bbdd(config, espec.nombre)
        raise

    return ResultadoGeneracion(
        nombre=espec.nombre,
        conexion=config.url(espec.nombre),
        orden=validado.orden,
        tablas=cargadas,
        ruta_dump=ruta_dump,
        id_registro=id_registro,
        segundos=round(time.perf_counter() - inicio, 3),
        script=validado.script,
    )
