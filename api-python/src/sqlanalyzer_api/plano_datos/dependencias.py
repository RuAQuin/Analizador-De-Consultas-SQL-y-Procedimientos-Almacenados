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
    columnas_padre: tuple[str, ...] # Vacío si el DDL no las indica: entonces referencia la PK de la tabla padre.
    # Desplazamiento de la FK en el DDL, para situar los errores.
    posicion: int = field(default=0, compare=False) # Se compara a False porque no influye para ser iguales.

    # ¿La tabla se hace referencia a si misma?
    @property
    def autorreferencia(self) -> bool:
        return self.tabla == self.tabla_padre


@dataclass(frozen=True)
class TablaOrdenada:
    tabla: str
    # Camino más largo
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


def kahn(nodos: list[str], aristas: set[tuple[str, str]]) -> tuple[list[tuple[str, int]], list[str]]:
    """Orden topológico de Kahn por oleadas sobre cualquier grafo.

    ``aristas`` son pares (padre, hija). Devuelve los nodos ordenados con su nivel
    y los que quedan sin ordenar por formar (o colgar de) un ciclo. A igualdad de
    nivel se respeta el orden de ``nodos``, para que el resultado sea siempre el mismo.
    Se usa para ordenar las tablas (paso 2.1) y los árboles (paso 2.3).
    """
    # Creación de los diccionarios padres e hijas.
    posicion = {n: i for i, n in enumerate(nodos)}
    padres: dict[str, set[str]] = {n: set() for n in nodos}
    hijas: dict[str, set[str]] = {n: set() for n in nodos}
    for padre, hija in aristas:
        padres[hija].add(padre)
        hijas[padre].add(hija)

    # Guarda cuántos padres le faltan a cada nodo por colocar.
    pendientes = {n: len(p) for n, p in padres.items()}
    oleada = [n for n in nodos if pendientes[n] == 0]
    orden: list[tuple[str, int]] = []
    nivel = 0 # Empezaremos las oleadas con los nodos sin padres (raíces).
    while oleada:
        orden.extend((n, nivel) for n in oleada)
        siguiente = []
        for n in oleada:
            for h in hijas[n]:
                pendientes[h] -= 1
                # En cada oleada desaparecen los nodos sin padres pendientes
                if pendientes[h] == 0:
                    siguiente.append(h)
        oleada = sorted(siguiente, key=posicion.__getitem__)
        # Por cada ronda que esté el nodo en la oleada se le sumará un nivel
        nivel += 1

    ordenados = {n for n, _ in orden}
    return orden, [n for n in nodos if n not in ordenados]


def _kahn(tablas: list[str], fks: list[ClaveForanea]) -> tuple[list[TablaOrdenada], list[str]]:
    """Kahn sobre las tablas: cada FK es una arista padre -> hija (sin autorreferencias)."""
    aristas = {(fk.tabla_padre, fk.tabla) for fk in fks if not fk.autorreferencia}
    orden, restantes = kahn(tablas, aristas)
    return [TablaOrdenada(t, nivel) for t, nivel in orden], restantes


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
        # Si una tabla está definida dos veces --> Error
        if tabla in inicio:
            errores.append(ErrorDdl(f"La tabla «{tabla}» está definida más de una vez",
                                    *linea_columna(ddl, raw.stmt_location or 0)))
            continue
        tablas.append(tabla)
        inicio[tabla] = raw.stmt_location or 0
        fks.extend(leer_fks(crear))

    # Comprueba que cada FK apunte a una tabla definida en el DDL.
    for fk in fks:
        if fk.tabla_padre not in inicio:
            errores.append(ErrorDdl(
                f"La FK de «{fk.tabla}» ({', '.join(fk.columnas)}) referencia la tabla «{fk.tabla_padre}», "
                "que no está definida en el DDL", *linea_columna(ddl, fk.posicion)))
    # Si ya se encuentran errores no merece la pena seguir.
    if errores:
        return Dependencias(claves_foraneas=fks, errores=errores)

    # Se ejecuta kahn
    orden, en_ciclo = _kahn(tablas, fks)
    #Si existe algún ciclo se marca.
    if en_ciclo:
        en_ciclo = _solo_ciclos(en_ciclo, fks)
        errores.append(ErrorDdl(
            "Hay un ciclo de FK entre las tablas " + ", ".join(f"«{t}»" for t in en_ciclo)
            + ": ninguna puede crearse antes que las demás", *linea_columna(ddl, inicio[en_ciclo[0]])))
    return Dependencias(claves_foraneas=fks, orden=orden, errores=errores, ciclo=en_ciclo)
