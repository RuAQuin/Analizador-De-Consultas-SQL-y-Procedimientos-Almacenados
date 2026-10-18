"""Paso 3 · Ordenación de las tablas según sus claves foráneas.

Primero las tablas padre y después sus hijas (orden topológico, algoritmo de
Kahn). Aunque las FK se crean al final, el orden es necesario para la carga: los
valores de una columna FK se toman de las claves ya insertadas en la tabla padre.
"""

from __future__ import annotations

from .especificacion import EspecificacionBbdd


class CicloDeClavesForaneas(ValueError):
    def __init__(self, tablas: list[str]):
        self.tablas = tablas
        super().__init__(f"las claves foráneas forman un ciclo entre las tablas: {', '.join(tablas)}")


def dependencias(espec: EspecificacionBbdd) -> dict[str, set[str]]:
    """Tabla -> conjunto de tablas padre de las que depende."""
    return {
        t.nombre: {c.fk.tabla for c in t.columnas if c.fk and c.fk.tabla != t.nombre}
        for t in espec.tablas
    }


def ordenar_tablas(espec: EspecificacionBbdd) -> list[str]:
    """Nombres de las tablas de padres a hijas. Respeta el orden original entre tablas independientes."""
    pendientes = {t: set(padres) for t, padres in dependencias(espec).items()}
    orden: list[str] = []
    while pendientes:
        listas = [t.nombre for t in espec.tablas if t.nombre in pendientes and not pendientes[t.nombre]]
        if not listas:
            raise CicloDeClavesForaneas(sorted(pendientes))
        for nombre in listas:
            orden.append(nombre)
            del pendientes[nombre]
        for padres in pendientes.values():
            padres.difference_update(listas)
    return orden
