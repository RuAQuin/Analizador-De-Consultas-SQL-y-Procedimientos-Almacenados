"""Paso 2.2 del módulo 1: FK de agrupación de cada tabla y formación de los árboles.

Parte del resultado del paso 2.1 (FK y nivel de Kahn de cada tabla):

- FK de agrupación: de las FK de una tabla, la que apunta al padre de nivel más alto.
  Si hay empate (varios padres con ese nivel, o dos FK al mismo padre), la primera
  del DDL. Las tablas sin padres (nivel 0) no tienen FK de agrupación: son raíces.
  Las FK de una tabla a sí misma no se tienen en cuenta.
- Árboles: cada raíz forma un árbol; cada tabla cuelga de la tabla a la que apunta su
  FK de agrupación. Así cada tabla pertenece a un único árbol.

Como el nivel de una tabla es el del padre más profundo + 1, la profundidad de una
tabla dentro de su árbol coincide con su nivel de Kahn.

El resto de FK (las que no son de agrupación) se resolverán al insertar los datos
apuntando a filas ya creadas; el paso 2.3 las usará para ordenar los árboles entre sí.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dependencias import ClaveForanea, Dependencias


@dataclass(frozen=True)
class NodoArbol:
    tabla: str
    # Tabla de la que cuelga en el árbol (None si es la raíz).
    padre: str | None
    # Nivel de Kahn.
    nivel: int
    # La FK que la une a su padre.
    fk_agrupacion: ClaveForanea | None


@dataclass(frozen=True)
class Arbol:
    # Nombre de la tabla raíz.
    raiz: str
    # Recorrido en preorden: cada tabla aparece antes que las que cuelgan de ella.
    nodos: list[NodoArbol] = field(default_factory=list)


def elegir_fks_agrupacion(dependencias: Dependencias) -> dict[str, ClaveForanea | None]:
    """FK de agrupación de cada tabla: la del padre de nivel más alto (None en las raíces)."""
    # Diccionario tabla-nivel.
    nivel = {o.tabla: o.nivel for o in dependencias.orden}
     # Iniciamos todas las tablas con None.
    elegidas: dict[str, ClaveForanea | None] = {t: None for t in nivel}
    # En orden del DDL: ante un empate gana la primera.
    for fk in dependencias.claves_foraneas:
        # Se salta las autorreferencias.
        if fk.autorreferencia:
            continue
        actual = elegidas[fk.tabla]
        # Si el padre es de un nivel mayor, se sustituye.
        if actual is None or nivel[fk.tabla_padre] > nivel[actual.tabla_padre]:
            elegidas[fk.tabla] = fk
    return elegidas


def formar_arboles(dependencias: Dependencias) -> list[Arbol]:
    """Forma un árbol por cada raíz colgando cada tabla de su FK de agrupación.

    Las raíces y las hijas de cada tabla siguen el orden de Kahn del paso 2.1.
    """
    agrupacion = elegir_fks_agrupacion(dependencias)
    nivel = {o.tabla: o.nivel for o in dependencias.orden}
    # Diccionario tabla->lista de tablas que cuelgan de ella.
    hijas: dict[str, list[str]] = {o.tabla: [] for o in dependencias.orden}
    for o in dependencias.orden:
        fk = agrupacion[o.tabla]
        if fk is not None:
            hijas[fk.tabla_padre].append(o.tabla)

    # Define un recorrido en profundidad recursivo.
    def recorrer(tabla: str, padre: str | None, nodos: list[NodoArbol]) -> None:
        nodos.append(NodoArbol(tabla, padre, nivel[tabla], agrupacion[tabla]))
        # Se recorre cada hija del nodo.
        for hija in hijas[tabla]:
            recorrer(hija, tabla, nodos)

    # Se rellena cada raíz con sus nodos.
    arboles = []
    for o in dependencias.orden:
        if agrupacion[o.tabla] is None:
            nodos: list[NodoArbol] = []
            recorrer(o.tabla, None, nodos)
            arboles.append(Arbol(o.tabla, nodos))
    return arboles
