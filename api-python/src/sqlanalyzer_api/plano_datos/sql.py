"""Utilidades para construir SQL de forma segura: identificadores, literales y tipos.

Los tipos de columna se interpretan con pglast en lugar de con expresiones
regulares: así se acepta cualquier forma válida de escribirlos (``int``,
``integer``, ``int4``...) y se rechaza cualquier texto que no sea solo un tipo
(por ejemplo, un intento de colar otra sentencia).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pglast import parse_sql
from pglast.ast import ColumnDef, CreateStmt
from pglast.keywords import COL_NAME_KEYWORDS, RESERVED_KEYWORDS, TYPE_FUNC_NAME_KEYWORDS
from pglast.parser import ParseError

_PALABRAS_A_ENTRECOMILLAR = RESERVED_KEYWORDS | TYPE_FUNC_NAME_KEYWORDS | COL_NAME_KEYWORDS


def ident(nombre: str) -> str:
    """Identificador listo para el SQL (los nombres ya vienen validados en minúsculas)."""
    return f'"{nombre}"' if nombre in _PALABRAS_A_ENTRECOMILLAR else nombre


def literal(valor: object) -> str:
    """Literal SQL de un valor de Python."""
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ValueError(f"valor numérico no válido: {valor}")
        return repr(valor)
    if isinstance(valor, str):
        if "\x00" in valor:
            raise ValueError("los textos no pueden contener el carácter NUL")
        return "'" + valor.replace("'", "''") + "'"
    raise ValueError(f"tipo de valor no admitido: {type(valor).__name__}")


# Nombre interno de PostgreSQL -> familia con la que se generan los datos.
_FAMILIAS = {
    "int2": "entero", "int4": "entero", "int8": "entero",
    "numeric": "decimal",
    "float4": "flotante", "float8": "flotante",
    "bool": "booleano",
    "date": "fecha",
    "timestamp": "marca_tiempo", "timestamptz": "marca_tiempo",
    "varchar": "texto", "bpchar": "texto", "text": "texto",
    "uuid": "uuid",
}

MAXIMO_ENTERO = {"int2": 32767, "int4": 2147483647, "int8": 9223372036854775807}

TIPOS_ADMITIDOS = (
    "smallint, integer, bigint, numeric(p,s), real, double precision, boolean, "
    "date, timestamp, timestamptz, varchar(n), char(n), text, uuid"
)


@dataclass(frozen=True)
class TipoColumna:
    texto: str                     # tal y como se escribe en el DDL
    nombre: str                    # nombre interno: int4, varchar, numeric...
    modificadores: tuple[int, ...]
    familia: str

    @property
    def maximo_entero(self) -> int:
        return MAXIMO_ENTERO[self.nombre]

    @property
    def longitud(self) -> int | None:
        """Longitud máxima de un texto (None = sin límite)."""
        if self.nombre == "bpchar":
            return self.modificadores[0] if self.modificadores else 1
        return self.modificadores[0] if self.modificadores else None

    @property
    def precision_escala(self) -> tuple[int | None, int]:
        """(precisión, escala) de un numeric; precisión None si no está acotada."""
        if not self.modificadores:
            return None, 2
        escala = self.modificadores[1] if len(self.modificadores) > 1 else 0
        return self.modificadores[0], escala


def analizar_tipo(texto: str) -> TipoColumna:
    """Interpreta el tipo de una columna con pglast. Lanza ValueError si no es válido."""
    try:
        sentencias = parse_sql(f"CREATE TABLE t (c {texto})")
    except ParseError as e:
        raise ValueError(f"tipo '{texto}' no válido: {e}") from None
    stmt = sentencias[0].stmt if len(sentencias) == 1 else None
    if (not isinstance(stmt, CreateStmt) or len(stmt.tableElts or ()) != 1
            or not isinstance(stmt.tableElts[0], ColumnDef)):
        raise ValueError(f"tipo '{texto}' no válido")
    columna = stmt.tableElts[0]
    nombre_tipo = columna.typeName
    if columna.constraints or columna.collClause or nombre_tipo.arrayBounds:
        raise ValueError(f"'{texto}' no es solo un tipo (no se admiten restricciones, COLLATE ni arrays)")

    nombre = nombre_tipo.names[-1].sval
    familia = _FAMILIAS.get(nombre)
    if familia is None:
        pista = " (usa identidad=true en su lugar)" if "serial" in nombre else ""
        raise ValueError(f"tipo '{texto}' no admitido{pista}. Tipos admitidos: {TIPOS_ADMITIDOS}")
    modificadores = tuple(m.val.ival for m in (nombre_tipo.typmods or ()))
    return TipoColumna(texto=texto.strip(), nombre=nombre, modificadores=modificadores, familia=familia)
