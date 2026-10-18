"""Paso 2 · Validación de la especificación y del DDL generado (antes de ejecutar nada).

1. Comprobaciones semánticas: tipos admitidos, rangos, que toda FK apunte a otra
   tabla existente y a una columna PK/UNQ de tipo compatible, que haya claves en
   el padre para las FK obligatorias, y que los INSERT recibidos sean de su tabla.
2. Ordenación de las tablas por sus FK (paso 3), que detecta los ciclos.
3. Generación del script completo (CREATE TABLE + INSERT + ALTER TABLE ... FOREIGN
   KEY) y análisis sintáctico con pglast.

Se acumulan todos los errores encontrados para devolverlos juntos a la WebApp.
"""

from __future__ import annotations

from dataclasses import dataclass

from pglast import parse_sql
from pglast.ast import InsertStmt
from pglast.parser import ParseError

from .datos import expresion_valor, literal_distribucion, sql_carga
from .ddl import claves_foraneas, crear_tabla
from .especificacion import EspecificacionBbdd, Tabla
from .ordenacion import CicloDeClavesForaneas, ordenar_tablas
from .sql import analizar_tipo


class ErrorValidacion(ValueError):
    def __init__(self, errores: list[str]):
        self.errores = errores
        super().__init__("La especificación no es válida:\n- " + "\n- ".join(errores))


@dataclass
class ScriptValidado:
    """Resultado de la validación: todo el SQL que se va a ejecutar, ya ordenado."""

    orden: list[str]                     # tablas de padres a hijas
    tablas: dict[str, str]               # tabla -> CREATE TABLE
    cargas: dict[str, str | None]        # tabla -> SQL de carga (None si 0 tuplas)
    claves_foraneas: list[str]           # ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY

    @property
    def script(self) -> str:
        partes = [self.tablas[t] for t in self.orden]
        partes += [self.cargas[t] for t in self.orden if self.cargas[t]]
        if self.claves_foraneas:
            partes.append("-- Claves foráneas (se añaden tras la carga para que sea más rápida)\n"
                          + "\n".join(self.claves_foraneas))
        return "\n\n".join(partes) + "\n"


def _validar_columnas(espec: EspecificacionBbdd, tabla: Tabla, errores: list[str]) -> None:
    prefijo = f"tabla '{tabla.nombre}', columna "
    for col in tabla.columnas:
        try:
            tipo = analizar_tipo(col.tipo)
        except ValueError as e:
            errores.append(f"{prefijo}'{col.nombre}': {e}")
            continue
        if col.identidad and tipo.familia != "entero":
            errores.append(f"{prefijo}'{col.nombre}': una columna identidad debe ser smallint, integer o bigint")
            continue
        if col.identidad or col.fk or tabla.inserts:
            continue
        try:
            expresion_valor(col, tipo, tabla.tuplas)
            for entrada in col.distribucion or ():
                literal_distribucion(entrada.valor, col, tipo)
        except ValueError as e:
            errores.append(f"tabla '{tabla.nombre}', columna {e}")


def _validar_fk(espec: EspecificacionBbdd, tabla: Tabla, errores: list[str]) -> None:
    for col in tabla.columnas:
        if not col.fk:
            continue
        origen = f"FK '{tabla.nombre}.{col.nombre}'"
        padre = espec.tabla(col.fk.tabla)
        if col.fk.tabla == tabla.nombre:
            errores.append(f"{origen}: debe apuntar a otra tabla, no a la propia")
            continue
        if padre is None:
            errores.append(f"{origen}: la tabla '{col.fk.tabla}' no existe en la especificación")
            continue
        destino = espec.destino_fk(col)
        if destino is None:
            if col.fk.columna:
                errores.append(f"{origen}: la columna '{padre.nombre}.{col.fk.columna}' no existe")
            else:
                errores.append(f"{origen}: indica la columna, '{padre.nombre}' no tiene una PK de una sola columna")
            continue
        _, referenciada = destino
        # PostgreSQL exige que la columna referenciada sea PK o UNIQUE (una PK compuesta no vale).
        if not (referenciada.unico or (referenciada.pk and len(padre.clave_primaria) == 1)):
            errores.append(f"{origen}: '{padre.nombre}.{referenciada.nombre}' no es PK ni UNQ")
        try:
            if analizar_tipo(col.tipo).familia != analizar_tipo(referenciada.tipo).familia:
                errores.append(f"{origen}: el tipo {col.tipo} no es compatible con "
                               f"{padre.nombre}.{referenciada.nombre} ({referenciada.tipo})")
        except ValueError:
            pass  # el tipo erróneo ya se informa en _validar_columnas
        if tabla.inserts or padre.inserts or tabla.tuplas == 0:
            continue  # con INSERT recibidos el número de claves no se conoce hasta la carga
        if padre.tuplas == 0 and not col.nulable:
            errores.append(f"{origen}: la tabla '{padre.nombre}' no tiene tuplas que referenciar")
        elif col.es_unica and tabla.tuplas > padre.tuplas:
            errores.append(f"{origen}: es única y '{tabla.nombre}' tiene más tuplas ({tabla.tuplas}) "
                           f"que '{padre.nombre}' ({padre.tuplas})")


def _validar_inserts(tabla: Tabla, errores: list[str]) -> None:
    if not tabla.inserts:
        if tabla.tuplas and all(c.identidad for c in tabla.columnas):
            errores.append(f"tabla '{tabla.nombre}': necesita alguna columna que no sea identidad para generar datos")
        return
    try:
        sentencias = parse_sql(tabla.inserts)
    except ParseError as e:
        errores.append(f"tabla '{tabla.nombre}': los INSERT no son SQL válido: {e}")
        return
    for s in sentencias:
        stmt = s.stmt
        if not isinstance(stmt, InsertStmt):
            errores.append(f"tabla '{tabla.nombre}': solo se admiten sentencias INSERT "
                           f"(se encontró {type(stmt).__name__})")
        elif stmt.relation.relname != tabla.nombre or stmt.relation.schemaname not in (None, "public"):
            errores.append(f"tabla '{tabla.nombre}': hay un INSERT dirigido a otra tabla "
                           f"('{stmt.relation.relname}')")


def validar(espec: EspecificacionBbdd) -> ScriptValidado:
    """Valida la especificación y devuelve el script ordenado. Lanza ErrorValidacion."""
    errores: list[str] = []
    for tabla in espec.tablas:
        _validar_columnas(espec, tabla, errores)
        _validar_fk(espec, tabla, errores)
        _validar_inserts(tabla, errores)
    if errores:
        raise ErrorValidacion(errores)

    try:
        orden = ordenar_tablas(espec)
    except CicloDeClavesForaneas as e:
        raise ErrorValidacion([str(e)]) from None

    validado = ScriptValidado(
        orden=orden,
        tablas={t.nombre: crear_tabla(t) for t in espec.tablas},
        cargas={t.nombre: sql_carga(espec, t) for t in espec.tablas},
        claves_foraneas=claves_foraneas(espec),
    )
    # Análisis sintáctico del DDL (y de la carga) con pglast antes de ejecutarlo.
    for sentencia in [*validado.tablas.values(), *filter(None, validado.cargas.values()),
                      *validado.claves_foraneas]:
        try:
            parse_sql(sentencia)
        except ParseError as e:
            errores.append(f"pglast rechaza el SQL generado: {e}\n{sentencia}")
    if errores:
        raise ErrorValidacion(errores)
    return validado
