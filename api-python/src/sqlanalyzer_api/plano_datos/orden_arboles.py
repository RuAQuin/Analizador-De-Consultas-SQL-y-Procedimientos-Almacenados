"""Paso 2.3 del módulo 1: Kahn entre árboles para decidir cuál se carga primero.

Dentro de un árbol, cada tabla se carga junto a la tabla de la que cuelga (su FK de
agrupación). El resto de FK ("referencias") apuntan a filas que ya deben existir: si una
tabla del árbol B referencia una tabla del árbol A, el árbol A tiene que cargarse antes.
Esas referencias son las aristas A -> B del grafo de árboles, que se ordena con Kahn.

Aunque las tablas no formen ciclos, los árboles sí pueden formarlos entre sí (una tabla
de A referencia a B y otra de B referencia a A). Ninguno de esos árboles puede cargarse
completo antes que el otro, así que se juntan en un mismo grupo de carga: sus tablas se
cargarán respetando el orden de Kahn de las tablas (paso 2.1), que siempre es válido.
Lo normal es que cada grupo tenga un único árbol.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .arboles import Arbol
from .dependencias import ClaveForanea, Dependencias, kahn


@dataclass(frozen=True)
class GrupoCarga:
    # Raíces de los árboles del grupo (más de una solo si los árboles forman un ciclo).
    arboles: list[str]
    # Nivel de Kahn entre árboles: 0 = no depende de ningún otro árbol.
    nivel: int
    # Raíces de los árboles (de otros grupos) que deben cargarse antes.
    depende_de: list[str] = field(default_factory=list)
    # FK que crean esas dependencias (de una tabla del grupo a una tabla de otro árbol).
    referencias: list[ClaveForanea] = field(default_factory=list)


def _alcanzables(origen: str, aristas: set[tuple[str, str]]) -> set[str]:
    """Recorrido en profundidad que devuelve todos los nodos a los que se puede llegar desde el origen.
    Sirve para detectar ciclos."""
    # Se guarda lo visitado y lo pendiente por visitar como una pila.
    vistos, pendientes = {origen}, [origen]
    # Por cada nodo que saca de la pila, recorre todas las aristas buscando las que salen de él.
    while pendientes:
        actual = pendientes.pop()
        for padre, hija in aristas:
            if padre == actual and hija not in vistos:
                vistos.add(hija)
                pendientes.append(hija)
    return vistos


def ordenar_arboles(dependencias: Dependencias, arboles: list[Arbol]) -> list[GrupoCarga]:
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

    # Árboles en ciclo: los que se alcanzan mutuamente forman un mismo grupo.
    alcance = {r: _alcanzables(r, aristas) for r in raices} # Todo lo que alcanza la raíz.
    grupo_de: dict[str, str] = {} # Relaciona cada árbol con su raíz.
    grupos: dict[str, list[str]] = {} # Relaciona la raíz del grupo con sus miembros.
    for r in raices:
        if r in grupo_de:
            continue
        miembros = [o for o in raices if o in alcance[r] and r in alcance[o]]
        grupos[r] = miembros
        for m in miembros:
            grupo_de[m] = r

    # Kahn entre grupos (sin ciclos por construcción); a igual nivel, el orden de los árboles.
    aristas_grupos = {(grupo_de[p], grupo_de[h]) for p, h in aristas if grupo_de[p] != grupo_de[h]}
    orden, _ = kahn(list(grupos), aristas_grupos)

    resultado = []
    for id_grupo, nivel in orden:
        miembros = grupos[id_grupo]
        # Referencias que salen de una tabla del grupo hacia una tabla de un árbol de fuera del grupo.
        externas = [fk for fk in referencias
                    if arbol_de[fk.tabla] in miembros and arbol_de[fk.tabla_padre] not in miembros]
        # Raíces de los árboles a los que apuntan esas FK.
        depende_de = [r for r in raices if any(arbol_de[fk.tabla_padre] == r for fk in externas)]
        resultado.append(GrupoCarga(miembros, nivel, depende_de, externas))
    return resultado
