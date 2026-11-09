"""Paso 2.3 del módulo 1: Kahn entre árboles para decidir cuál se carga primero.

Dentro de un árbol, cada tabla se carga junto a la tabla de la que cuelga (su FK de
agrupación). El resto de FK ("referencias") apuntan a filas que ya deben existir: si una
tabla del árbol B referencia una tabla del árbol A, el árbol A tiene que cargarse antes.
Esas referencias son las aristas A -> B del grafo de árboles, que se ordena con Kahn.

Aunque las tablas no formen ciclos, los árboles sí pueden formarlos entre sí (una tabla
de A referencia a B y otra de B referencia a A). En ese caso ninguno puede cargarse antes
que el otro: se devuelve un error para que el usuario corrija el DDL.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .arboles import Arbol
from .ddl import ErrorDdl, linea_columna
from .dependencias import ClaveForanea, Dependencias, describir_fk, kahn, solo_ciclos


@dataclass(frozen=True)
class ArbolOrdenado:
    # Raíz del árbol.
    raiz: str
    # Nivel de Kahn entre árboles: 0 = no depende de ningún otro árbol.
    nivel: int
    # Raíces de los árboles que deben cargarse antes.
    depende_de: list[str] = field(default_factory=list)
    # FK que crean esas dependencias (de una tabla de este árbol a una tabla de otro árbol).
    referencias: list[ClaveForanea] = field(default_factory=list)


@dataclass(frozen=True)
class OrdenArboles:
    orden: list[ArbolOrdenado] = field(default_factory=list)
    errores: list[ErrorDdl] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores


def _hay_ciclo(dependencias: Dependencias, agrupacion: dict[str, ClaveForanea | None]) -> bool:
    """¿Forman ciclo los árboles que salen de esta elección de FK de agrupación?"""
    def raiz(tabla: str) -> str:
        while agrupacion[tabla] is not None:
            tabla = agrupacion[tabla].tabla_padre
        return tabla

    arbol_de = {t: raiz(t) for t in agrupacion}
    aristas = {(arbol_de[fk.tabla_padre], arbol_de[fk.tabla]) for fk in dependencias.claves_foraneas
               if not fk.autorreferencia and fk != agrupacion[fk.tabla]
               and arbol_de[fk.tabla] != arbol_de[fk.tabla_padre]}
    _, en_ciclo = kahn(list(dict.fromkeys(arbol_de.values())), aristas)
    return bool(en_ciclo)


def _recomendacion(dependencias: Dependencias, agrupacion: dict[str, ClaveForanea | None],
                   causantes: list[ClaveForanea]) -> str:
    """Cómo romper el ciclo cambiando el orden de las columnas FK de una tabla.

    Si una tabla tiene dos padres del mismo nivel, la FK de agrupación es la primera del
    DDL: escribir antes la otra FK cambia la tabla de árbol. Solo se proponen los cambios
    que de verdad rompen el ciclo; si no hay ninguno, se recomienda eliminar una FK.
    """
    nivel = {o.tabla: o.nivel for o in dependencias.orden}
    propuestas = []
    for fk in causantes:
        actual = agrupacion[fk.tabla]
        if nivel[fk.tabla_padre] != nivel[actual.tabla_padre]:
            continue  # Cambiar el orden no cambiaría la FK de agrupación.
        if not _hay_ciclo(dependencias, {**agrupacion, fk.tabla: fk}):
            propuestas.append(f"en «{fk.tabla}», escribe {', '.join(fk.columnas)} (→ «{fk.tabla_padre}») "
                              f"antes que {', '.join(actual.columnas)} (→ «{actual.tabla_padre}»)")
    if propuestas:
        return "Para corregirlo, cambia el orden de las columnas FK de una de estas tablas: " + "; ".join(propuestas)
    return "Para corregirlo, elimina una de estas FK: " + "; ".join(describir_fk(fk) for fk in causantes)


def ordenar_arboles(dependencias: Dependencias, arboles: list[Arbol], ddl: str) -> OrdenArboles:
    """Ordena los árboles con Kahn según las FK que van de un árbol a otro."""
    # Diccionarios auxiliares
    arbol_de = {n.tabla: a.raiz for a in arboles for n in a.nodos} # Tabla --> Raíz
    agrupacion = {n.tabla: n.fk_agrupacion for a in arboles for n in a.nodos} # Tabla --> FK de agrupación a su padre.
    raices = [a.raiz for a in arboles] # Lista de raíces.

    # Referencias entre árboles: FK que no son de agrupación ni autorreferencias.
    referencias = [fk for fk in dependencias.claves_foraneas
                   if not fk.autorreferencia and fk != agrupacion[fk.tabla] # No son autorreferencias ni la FK de agrupacion.
                   and arbol_de[fk.tabla] != arbol_de[fk.tabla_padre]] # Van de un árbol a otro.
    aristas = {(arbol_de[fk.tabla_padre], arbol_de[fk.tabla]) for fk in referencias} # Pares árbol padre - árbol hijo.

    # Kahn entre árboles; a igual nivel, el orden de los árboles.
    orden, en_ciclo = kahn(raices, aristas)

    # Si los árboles forman un ciclo, es un error: no se intenta resolver, se recomienda cómo corregirlo.
    if en_ciclo:
        en_ciclo = solo_ciclos(en_ciclo, aristas)
        causantes = [fk for fk in referencias if arbol_de[fk.tabla] in en_ciclo and arbol_de[fk.tabla_padre] in en_ciclo]
        detalle = "; ".join(describir_fk(fk) for fk in causantes)
        return OrdenArboles(errores=[ErrorDdl(
            "Hay un ciclo entre los árboles " + ", ".join(f"«{r}»" for r in en_ciclo)
            + f": ninguno puede cargarse antes que los demás ({detalle}). "
            + _recomendacion(dependencias, agrupacion, causantes),
            *linea_columna(ddl, causantes[0].posicion))])

    resultado = []
    for raiz, nivel in orden:
        # Referencias que salen de una tabla de este árbol hacia otro árbol.
        externas = [fk for fk in referencias if arbol_de[fk.tabla] == raiz]
        # Raíces de los árboles a los que apuntan esas FK.
        depende_de = [r for r in raices if any(arbol_de[fk.tabla_padre] == r for fk in externas)]
        resultado.append(ArbolOrdenado(raiz, nivel, depende_de, externas))
    return OrdenArboles(orden=resultado)
