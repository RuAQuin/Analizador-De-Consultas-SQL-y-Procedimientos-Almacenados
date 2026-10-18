"""Línea de órdenes del generador de BBDD.

    python -m sqlanalyzer_api.plano_datos ejemplos/compras.json --validar
    python -m sqlanalyzer_api.plano_datos ejemplos/compras.json [--reemplazar] [--sin-exportar] [--sin-registrar]

La conexión a PostgreSQL se configura con variables de entorno (ver README).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from pydantic import ValidationError

from ..config import ConfigPostgres
from .especificacion import EspecificacionBbdd
from .generador import generar_bbdd
from .validacion import ErrorValidacion, validar


def _leer_especificacion(origen: str) -> EspecificacionBbdd:
    texto = sys.stdin.read() if origen == "-" else Path(origen).read_text(encoding="utf-8")
    try:
        return EspecificacionBbdd.model_validate_json(texto)
    except ValidationError as e:
        errores = [f"{'.'.join(map(str, err['loc'])) or 'especificación'}: {err['msg']}" for err in e.errors()]
        raise ErrorValidacion(errores) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sqlanalyzer_api.plano_datos",
                                     description="Genera una BBDD PostgreSQL a partir de su especificación JSON.")
    parser.add_argument("especificacion", help="fichero JSON con la especificación ('-' para leer de stdin)")
    parser.add_argument("--validar", action="store_true",
                        help="solo valida y muestra el script SQL ordenado, sin conectar a PostgreSQL")
    parser.add_argument("--reemplazar", action="store_true", help="elimina la BBDD si ya existe")
    parser.add_argument("--sin-exportar", action="store_true", help="no ejecuta pg_dump")
    parser.add_argument("--sin-registrar", action="store_true", help="no la registra en el repositorio")
    args = parser.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)

    try:
        espec = _leer_especificacion(args.especificacion)
        if args.validar:
            validado = validar(espec)
            print(f"-- Orden de creación: {' -> '.join(validado.orden)}\n")
            print(validado.script)
            return 0
        resultado = generar_bbdd(espec, ConfigPostgres.desde_entorno(), reemplazar=args.reemplazar,
                                 exportar=not args.sin_exportar, registrar=not args.sin_registrar)
    except ErrorValidacion as e:
        print(e, file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - la CLI informa de cualquier fallo de ejecución
        print(f"Error generando la BBDD: {e}", file=sys.stderr)
        return 2

    salida = asdict(resultado)
    salida.pop("script")
    print(json.dumps(salida, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
