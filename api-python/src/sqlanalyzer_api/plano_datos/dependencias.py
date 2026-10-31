"""Paso 2.1 del módulo 1: se leen las FK del DDL y se ordenan las tablas con Kahn.

Cada FK es una arista padre -> hija. El algoritmo de Kahn recorre el grafo por
oleadas: primero las tablas sin padres (nivel 0), luego las que solo dependen de
ellas (nivel 1), etc. El nivel de una tabla es la longitud del camino más largo
desde una raíz, y se usará en el paso 2.2 para elegir la FK de agrupación.

Como el DDL solo admite CREATE TABLE, PostgreSQL exige que cada tabla padre exista
antes que su hija: una FK a una tabla no definida o un ciclo entre tablas harían
fallar la creación, así que se devuelven como errores para que el usuario corrija
el DDL. Las FK de una tabla a sí misma sí se permiten y no cuentan para el orden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pglast import ast, enums

from .ddl import ErrorDdl, linea_columna, nombre_tabla


@dataclass(frozen=True)
class ClaveForanea:
    tabla: str # Tabla hija
    columnas: tuple[str, ...] # Columnas que forman la FK
    tabla_padre: str
    # Vacío si el DDL no las indica: entonces referencia la PK de la tabla padre.
    columnas_padre: tuple[str, ...]
    # Desplazamiento de la FK en el DDL, para situar los errores.
    posicion: int = field(default=0, compare=False) # Se compara a False porque no influye para ser iguales.

    @property
    def autorreferencia(self) -> bool:
        return self.tabla == self.tabla_padre


@dataclass(frozen=True)
class TablaOrdenada:
    tabla: str
    nivel: int


@dataclass(frozen=True)
class Dependencias:
    claves_foraneas: list[ClaveForanea] = field(default_factory=list)
    # Orden topológico de Kahn: los padres siempre antes que sus hijas.
    orden: list[TablaOrdenada] = field(default_factory=list)
    errores: list[ErrorDdl] = field(default_factory=list)
    # Tablas que forman un ciclo de FK (vacío si no hay). En caso de ciclo, se debe crear una tabla intermedia.
    ciclo: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores


# Comprueba que la restricción es FK.
def _es_fk(restriccion) -> bool:
    return isinstance(restriccion, ast.Constraint) and restriccion.contype == enums.ConstrType.CONSTR_FOREIGN

# Devuelve los nombres de las columnas.
def _nombres(lista) -> tuple[str, ...]:
    return tuple(n.sval for n in lista or ())


def leer_fks(crear: ast.CreateStmt) -> list[ClaveForanea]:
    """FK de una sentencia CREATE TABLE, tanto de columna (REFERENCES) como de tabla (FOREIGN KEY)."""
    tabla = nombre_tabla(crear.relation)
    fks = []
    for elemento in crear.tableElts or ():
        if isinstance(elemento, ast.ColumnDef):
            # FK de columna: la columna local es la propia columna.
            for r in elemento.constraints or ():
                if _es_fk(r):
                    fks.append(ClaveForanea(tabla, (elemento.colname,), nombre_tabla(r.pktable),
                                            _nombres(r.pk_attrs), r.location or 0))
        elif _es_fk(elemento):
            # FK fuera de la columa: FOREIGN KEY (a, b) REFERENCES t (x, y).
            fks.append(ClaveForanea(tabla, _nombres(elemento.fk_attrs), nombre_tabla(elemento.pktable),
                                    _nombres(elemento.pk_attrs), elemento.location or 0))
    return fks


def _kahn(tablas: list[str], fks: list[ClaveForanea]) -> tuple[list[TablaOrdenada], list[str]]:
    """Orden topológico por oleadas. Devuelve el orden y las tablas que quedan en un ciclo.

    A igualdad de nivel se respeta el orden en que aparecen en el DDL, para que
    el resultado sea siempre el mismo.
    """
    posicion = {t: i for i, t in enumerate(tablas)}
    padres: dict[str, set[str]] = {t: set() for t in tablas}
    hijas: dict[str, set[str]] = {t: set() for t in tablas}
    for fk in fks:
        if not fk.autorreferencia:
            padres[fk.tabla].add(fk.tabla_padre)
            hijas[fk.tabla_padre].add(fk.tabla)

    pendientes = {t: len(p) for t, p in padres.items()}
    oleada = [t for t in tablas if pendientes[t] == 0]
    orden: list[TablaOrdenada] = []
    nivel = 0
    while oleada:
        orden.extend(TablaOrdenada(t, nivel) for t in oleada)
        siguiente = []
        for t in oleada:
            for h in hijas[t]:
                pendientes[h] -= 1
                if pendientes[h] == 0:
                    siguiente.append(h)
        oleada = sorted(siguiente, key=posicion.__getitem__)
        nivel += 1

    ordenadas = {o.tabla for o in orden}
    return orden, [t for t in tablas if t not in ordenadas]


def _solo_ciclos(restantes: list[str], fks: list[ClaveForanea]) -> list[str]:
    """De las tablas que Kahn no pudo ordenar, quita las que solo cuelgan de un ciclo sin formar parte de él."""
    quedan = set(restantes)
    hijas = {t: {fk.tabla for fk in fks if fk.tabla_padre == t and not fk.autorreferencia} for t in quedan}
    while True:
        sin_hijas = {t for t in quedan if not hijas[t] & quedan}
        if not sin_hijas:
            return [t for t in restantes if t in quedan]
        quedan -= sin_hijas


def analizar_dependencias(sentencias: tuple[ast.RawStmt, ...], ddl: str) -> Dependencias:
    """Lee las FK de las sentencias ya parseadas (paso 1) y ordena las tablas con Kahn."""
    tablas: list[str] = []
    inicio: dict[str, int] = {}
    fks: list[ClaveForanea] = []
    errores: list[ErrorDdl] = []

    for raw in sentencias:
        crear = raw.stmt
        tabla = nombre_tabla(crear.relation)
        if tabla in inicio:
            errores.append(ErrorDdl(f"La tabla «{tabla}» está definida más de una vez",
                                    *linea_columna(ddl, raw.stmt_location or 0)))
            continue
        tablas.append(tabla)
        inicio[tabla] = raw.stmt_location or 0
        fks.extend(leer_fks(crear))

    for fk in fks:
        if fk.tabla_padre not in inicio:
            errores.append(ErrorDdl(
                f"La FK de «{fk.tabla}» ({', '.join(fk.columnas)}) referencia la tabla «{fk.tabla_padre}», "
                "que no está definida en el DDL", *linea_columna(ddl, fk.posicion)))
    if errores:
        return Dependencias(claves_foraneas=fks, errores=errores)

    orden, en_ciclo = _kahn(tablas, fks)
    if en_ciclo:
        en_ciclo = _solo_ciclos(en_ciclo, fks)
        errores.append(ErrorDdl(
            "Hay un ciclo de FK entre las tablas " + ", ".join(f"«{t}»" for t in en_ciclo)
            + ": ninguna puede crearse antes que las demás", *linea_columna(ddl, inicio[en_ciclo[0]])))
    return Dependencias(claves_foraneas=fks, orden=orden, errores=errores, ciclo=en_ciclo)
