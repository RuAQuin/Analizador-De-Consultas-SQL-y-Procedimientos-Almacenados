"""Resolución automática de ciclos de FK mediante tablas intermedias.

Si las FK forman un ciclo (p. ej. departamentos.responsable_id -> empleados y
empleados.departamento_id -> departamentos), ninguna tabla puede crearse antes que
las demás. El sistema rompe cada ciclo sacando una de sus FK a una tabla intermedia,
sin que el usuario tenga que reescribir el DDL:

    departamentos (id PK, ..., responsable_id -> empleados)
pasa a
    departamentos (id PK, ...)
    departamentos_responsable (departamentos_id PK -> departamentos, responsable_id NOT NULL -> empleados)

La PK de la tabla intermedia es la de la tabla hija, así que cada fila sigue teniendo
como mucho un valor (la relación N:1 se conserva). Las tablas que no cambian conservan
el texto que escribió el usuario.

Qué FK se aparta: entre las FK del ciclo que pueden pasarse a una tabla intermedia, la
primera que apunta a una tabla escrita más abajo en el DDL (el usuario escribe primero
la tabla que espera crear antes); si no hay ninguna, la primera del DDL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pglast import ast, enums, parse_sql
from pglast.stream import IndentedStream, RawStream
from pglast.visitors import Visitor

from .ddl import ErrorDdl, nombre_tabla
from .dependencias import ClaveForanea, _solo_ciclos, leer_fks

# Tipos seriales: en la tabla intermedia la columna referencia un valor ya generado.
# Traducción al tipo base (los seriales sirven para hacer secuencias).
_SERIALES = {"smallserial": "smallint", "serial2": "smallint", "serial": "integer",
             "serial4": "integer", "bigserial": "bigint", "serial8": "bigint"}
# Restricciones de columna que se pueden trasladar con la FK a la tabla intermedia.
_TRASLADABLES = {enums.ConstrType.CONSTR_NOTNULL, enums.ConstrType.CONSTR_NULL,
                 enums.ConstrType.CONSTR_FOREIGN, enums.ConstrType.CONSTR_UNIQUE}


@dataclass(frozen=True)
class TablaIntermedia:
    tabla: str
    # FK original que sustituye.
    sustituye: ClaveForanea
    # Guarda el CREATE TABLE...
    ddl: str


@dataclass(frozen=True)
class ResolucionCiclos:
    # DDL con los ciclos resueltos (igual al original si no había ciclos).
    ddl: str
    # Tablas intermedias.
    intermedias: list[TablaIntermedia] = field(default_factory=list)
    # Errores.
    errores: list[ErrorDdl] = field(default_factory=list)


class _Columnas(Visitor):
    """Nombres de las columnas que aparecen en una expresión (p. ej. un CHECK)."""

    def __init__(self):
        self.nombres: set[str] = set()

    def visit_ColumnRef(self, ancestors, node):
        if isinstance(node.fields[-1], ast.String):
            self.nombres.add(node.fields[-1].sval)


def _columnas_en(expresion) -> set[str]:
    if expresion is None:
        return set()
    # Recoge las columnas de las tablas de cada expresión del DDL
    v = _Columnas()
    v(expresion)
    # Devuelve las columnas que se usan en el DDL.
    return v.nombres


# Convierte el nodo en una tupla de String.
def _nombres(lista) -> tuple[str, ...]:
    return tuple(n.sval for n in lista or ())

# Diccionario nombre_columa --> ColumnDef
def _definiciones(crear: ast.CreateStmt) -> dict[str, ast.ColumnDef]:
    return {e.colname: e for e in crear.tableElts or () if isinstance(e, ast.ColumnDef)}


# Devuelve las columnas de la PK
def _clave_primaria(crear: ast.CreateStmt) -> tuple[str, ...]:
    for e in crear.tableElts or ():
        if isinstance(e, ast.ColumnDef):
            # Definición en columna
            if any(c.contype == enums.ConstrType.CONSTR_PRIMARY for c in e.constraints or ()):
                return (e.colname,)
        elif isinstance(e, ast.Constraint) and e.contype == enums.ConstrType.CONSTR_PRIMARY:
            # Definición en tabla
            return _nombres(e.keys)
    return ()

# Escribe el tipo y cambia los seriales a su valor base.
def _tipo(columna: ast.ColumnDef) -> str:
    tipo = RawStream()(columna.typeName)
    return _SERIALES.get(tipo.lower(), tipo)


def _motivo_no_trasladable(crear: ast.CreateStmt, fk: ClaveForanea) -> str | None:
    """Por qué esta FK no puede pasarse a una tabla intermedia (None si sí puede)."""
    pk = _clave_primaria(crear)
    # No hay PK
    if not pk:
        return f"«{fk.tabla}» no tiene PK"
    # Una columna de la FK forma parte de la PK padre
    if set(fk.columnas) & set(pk):
        return f"la FK de «{fk.tabla}» ({', '.join(fk.columnas)}) forma parte de su PK"
    definiciones = _definiciones(crear)
    for col in fk.columnas:
        # La columna no existe
        if col not in definiciones:
            return f"la columna «{col}» no está definida en «{fk.tabla}»"
        extra = [c for c in definiciones[col].constraints or () if c.contype not in _TRASLADABLES]
        # Hay restricciones no trasladables
        if extra or definiciones[col].raw_default is not None:
            return f"la columna «{fk.tabla}.{col}» tiene restricciones (DEFAULT, CHECK...) que no se pueden trasladar"
    # Las columnas de la FK se usan en otra restricción de tabla
    for e in crear.tableElts or ():
        # Si es una restricción de tabla
        if isinstance(e, ast.Constraint):
            es_esta_fk = (e.contype == enums.ConstrType.CONSTR_FOREIGN and _nombres(e.fk_attrs) == fk.columnas
                          and nombre_tabla(e.pktable) == fk.tabla_padre)
            usadas = set(_nombres(e.keys)) | set(_nombres(e.fk_attrs)) | _columnas_en(e.raw_expr)
            if not es_esta_fk and usadas & set(fk.columnas):
                return f"las columnas de la FK de «{fk.tabla}» se usan en otras restricciones de la tabla"
        # Si la restricción está escrita en la línea de otra columna.
        elif isinstance(e, ast.ColumnDef) and e.colname not in fk.columnas:
            for c in e.constraints or ():
                if _columnas_en(c.raw_expr) & set(fk.columnas):
                    return f"las columnas de la FK de «{fk.tabla}» se usan en otras restricciones de la tabla"
    return None


def _alcanzable(origen: str, destino: str, aristas: list[ClaveForanea]) -> bool:
    """¿Se llega de ``origen`` a ``destino`` siguiendo aristas padre -> hija?"""
    pendientes, vistos = [origen], {origen}
    while pendientes:
        actual = pendientes.pop()
        if actual == destino:
            return True
        for fk in aristas: # Se recorren todas las aristas
            if fk.tabla_padre == actual and fk.tabla not in vistos:
                vistos.add(fk.tabla)
                pendientes.append(fk.tabla)
    return False


def _sin_ordenar(tablas: list[str], aristas: list[ClaveForanea]) -> list[str]:
    """Tablas que Kahn no puede ordenar con estas aristas."""
    pendientes = {t: {fk.tabla_padre for fk in aristas if fk.tabla == t} for t in tablas}
    hechas: set[str] = set()
    cambio = True
    while cambio:
        cambio = False
        for t in tablas:
            # Si no tienen tablas pendientes para su creación se añaden a hechas.
            if t not in hechas and pendientes[t] <= hechas:
                hechas.add(t)
                cambio = True
    return [t for t in tablas if t not in hechas]


def _sql_intermedia(nombre: str, hija: ast.CreateStmt, fk: ClaveForanea, pk: tuple[str, ...]) -> str:
    """Escribe el CREATE TABLE de la tabla intermedia a partir de la hija, la FK y su PK."""
    definiciones = _definiciones(hija)
    unica = any(c.contype == enums.ConstrType.CONSTR_UNIQUE
                for col in fk.columnas for c in definiciones[col].constraints or ())
    # Columnas de la tabla intermedia: PK de la hija (con prefijo) + columnas de la FK.
    cols_pk = [f"{fk.tabla.split('.')[-1]}_{c}" for c in pk] # Nombre Tabla + PK
    cols_fk = [c if c not in cols_pk else f"{c}_ref" for c in fk.columnas] # Nombre FK (si ya existe se añade _red)
    padre_cols = f" ({', '.join(fk.columnas_padre)})" if fk.columnas_padre else ""

    # Creación de la tabla manteniendo sus restricciones
    lineas = []
    # PK simple --> Una sola línea con PRIMARY KEY REFERENCES hija (pk)
    if len(pk) == 1:
        lineas.append(f"{cols_pk[0]} {_tipo(definiciones[pk[0]])} PRIMARY KEY REFERENCES {fk.tabla} ({pk[0]})")
    # PK compuesta --> Columnas NOT NULL
    else:
        lineas += [f"{c} {_tipo(definiciones[o])} NOT NULL" for c, o in zip(cols_pk, pk)]
    # FK simple --> NOT NULL + REFERENCES padre
    if len(fk.columnas) == 1:
        lineas.append(f"{cols_fk[0]} {_tipo(definiciones[fk.columnas[0]])} NOT NULL"
                      f"{' UNIQUE' if unica else ''} REFERENCES {fk.tabla_padre}{padre_cols}")
    # FK compuesta --> columnas NOT NULL.
    else:
        lineas += [f"{c} {_tipo(definiciones[o])} NOT NULL" for c, o in zip(cols_fk, fk.columnas)]
    # PK compuesta --> PRIMARY KEY compuesta al final + FOREIGN KEY de la tabla
    if len(pk) > 1:
        lineas.append(f"PRIMARY KEY ({', '.join(cols_pk)})")
        lineas.append(f"FOREIGN KEY ({', '.join(cols_pk)}) REFERENCES {fk.tabla} ({', '.join(pk)})")
    # FK compuesta --> FOREIGN KEY de tabla.
    if len(fk.columnas) > 1:
        if unica:
            lineas.append(f"UNIQUE ({', '.join(cols_fk)})")
        lineas.append(f"FOREIGN KEY ({', '.join(cols_fk)}) REFERENCES {fk.tabla_padre}{padre_cols}")
    # Se conservan los UNIQUES

    # Se devuelve la tabla intermedia con el aviso pertinente
    return (f"-- Tabla intermedia creada automáticamente para romper un ciclo de FK:\n"
            f"-- sustituye a {fk.tabla} ({', '.join(fk.columnas)}) -> {fk.tabla_padre}\n"
            f"CREATE TABLE {nombre} (\n  " + ",\n  ".join(lineas) + "\n)")


def _quitar_fk(crear: ast.CreateStmt, fk: ClaveForanea) -> None:
    """Modifico la tabla hija de la FK apartada, que pasa a ser padre de la tabla intermedia."""
    def se_queda(e) -> bool:
        if isinstance(e, ast.ColumnDef):
            return e.colname not in fk.columnas
        return not (e.contype == enums.ConstrType.CONSTR_FOREIGN and _nombres(e.fk_attrs) == fk.columnas
                    and nombre_tabla(e.pktable) == fk.tabla_padre)
    crear.tableElts = tuple(e for e in crear.tableElts if se_queda(e))


# Recorta el texto de una sentencia de un DDL original.
def _texto(ddl: str, raw: ast.RawStmt) -> str:
    inicio = raw.stmt_location or 0
    return (ddl[inicio:inicio + raw.stmt_len] if raw.stmt_len else ddl[inicio:]).strip()


def resolver_ciclos(ddl: str) -> ResolucionCiclos:
    """Rompe los ciclos de FK del DDL con tablas intermedias.

    Se llama con un DDL ya validado en el paso 1 y sin FK a tablas inexistentes.
    Se vuelve a parsear para poder modificar el árbol sin tocar el del paso 1.
    """
    # Parseo del DDL.
    sentencias = parse_sql(ddl)
    creates = {nombre_tabla(r.stmt.relation): r.stmt for r in sentencias}
    tablas = list(creates)
    fks = [fk for crear in creates.values() for fk in leer_fks(crear)]
    posicion = {t: i for i, t in enumerate(tablas)}

    aristas = [fk for fk in fks if not fk.autorreferencia] # Si se referencian a la misma
    apartadas: list[ClaveForanea] = []
    # Se comprueba si hay ciclos, si no hay ciclos se salta el bucle.
    while en_ciclo := _sin_ordenar(tablas, aristas):
        candidatas = []
        for fk in aristas:
            # La FK está en un ciclo si desde su hija se vuelve a su padre.
            # Si no es alcanzable, su división no rompe el ciclo
            if fk.tabla in en_ciclo and fk.tabla_padre in en_ciclo \
                    and _alcanzable(fk.tabla, fk.tabla_padre, aristas) \
                    and fk not in apartadas and _motivo_no_trasladable(creates[fk.tabla], fk) is None:
                candidatas.append(fk)
        if not candidatas:
            motivos = sorted({_motivo_no_trasladable(creates[fk.tabla], fk) for fk in aristas
                              if fk.tabla in en_ciclo and fk.tabla_padre in en_ciclo} - {None})
            return ResolucionCiclos(ddl, errores=[ErrorDdl(
                "Hay un ciclo de FK entre las tablas " + ", ".join(f"«{t}»" for t in _solo_ciclos(en_ciclo, aristas))
                + " y no se puede romper automáticamente con una tabla intermedia: " + "; ".join(motivos))])
        # Preferencia: FK hacia una tabla escrita más abajo en el DDL; luego, orden del DDL.
        elegida = min(candidatas, key=lambda fk: (posicion[fk.tabla_padre] < posicion[fk.tabla], fks.index(fk)))
        apartadas.append(elegida)
        aristas = [fk for fk in aristas if fk != elegida]

    # Se devuelve el DDL original sin intermedios ni errores.
    if not apartadas:
        return ResolucionCiclos(ddl)

    # Creación de la tabla intermedia
    usados = set(tablas)
    intermedias: list[TablaIntermedia] = []
    for fk in apartadas:
        hija = creates[fk.tabla]
        pk = _clave_primaria(hija)
        # El sufijo es el nombre de la columna sin _id
        sufijo = fk.columnas[0].removesuffix("_id") if len(fk.columnas) == 1 else fk.tabla_padre.split(".")[-1]
        nombre = base = f"{fk.tabla}_{sufijo}"
        n = 2
        # Si el nombre ya existe prueba _2, _3
        while nombre in usados:
            nombre, n = f"{base}_{n}", n + 1
        usados.add(nombre)
        intermedias.append(TablaIntermedia(nombre, fk, _sql_intermedia(nombre, hija, fk, pk)))

    # Se modifican las hijas después de generar las intermedias.
    modificadas = set()
    for fk in apartadas:
        _quitar_fk(creates[fk.tabla], fk)
        modificadas.add(fk.tabla)

    # Partes modificadas de las tablas.
    partes = []
    for raw in sentencias:
        tabla = nombre_tabla(raw.stmt.relation)
        # Las tablas modificadas se reescriben desde el AST y las que no se mantienen tal cual.
        partes.append(IndentedStream()(raw) if tabla in modificadas else _texto(ddl, raw))
    # Las tablas intermedias se añaden al final.
    partes += [i.ddl for i in intermedias]
    return ResolucionCiclos(";\n\n".join(partes) + ";\n", intermedias)
