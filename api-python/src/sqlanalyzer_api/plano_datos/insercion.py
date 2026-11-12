"""Paso 6 del módulo 1: inserción de datos (sub-diagrama «Inserción de datos» del esquema funcional).

Se divide en tres pasos:

- 6.1. Recorrer los árboles en orden de carga (bucle exterior): «Siguiente árbol» … «¿Último árbol?».
  HECHO: ``recorrer_arboles``.
- 6.2. Generar las tuplas de cada árbol en profundidad (bucles interiores): «Generamos tupla»
  (id = contador + 1) → «¿La tupla tiene hijos?» → «Generamos tupla en la tabla hija» → «¿Quedan tuplas
  por construir?» → «¿Existe tabla padre?». HECHO: ``generar_tuplas`` y ``generar_carga``.
- 6.3. Escribir las tuplas en PostgreSQL. PENDIENTE.

Las tuplas salen del mismo ``Generador`` que la vista previa del paso 3, así que lo insertado coincide con
lo que el usuario ha confirmado. Como la FK de agrupación reparte las hijas en bloques consecutivos,
el recorrido en profundidad genera cada tabla en orden: la tupla de la fila i tiene id = contador + 1.

Mientras 6.3 no esté hecho, no se inserta nada: la BBDD creada en el paso 5 queda con las tablas vacías.
Al implementarlo hay que tener en cuenta (marcado con PENDIENTE 6.3 en el código):

- PENDIENTE 6.3 · FK dentro del mismo árbol: el orden de carga solo garantiza el orden ENTRE árboles.
  Una FK que no es de agrupación entre dos tablas del mismo árbol (envios → direcciones, las dos en el
  árbol de clientes) apunta a una tupla que el recorrido en profundidad puede no haber generado aún. Su
  valor ya es correcto (se calcula con el número de fila), pero hay que insertar tabla a tabla en el
  orden de Kahn (paso 2.1) aunque las tuplas se generen en profundidad.
- PENDIENTE 6.3 · Columnas serial/IDENTITY: el 6.2 les da valor (id = contador + 1) para que las FK
  cuadren. Al insertar, con GENERATED ALWAYS hay que usar OVERRIDING SYSTEM VALUE, y al final ajustar
  la secuencia (setval) para que los siguientes INSERT del usuario no repitan ids.
- PENDIENTE 6.3 · Valores ``AUTO`` (DEFAULT que no es un número, columnas GENERATED ... STORED): se dejan
  fuera del INSERT para que los rellene PostgreSQL.
- PENDIENTE 6.3 · Fallos de PostgreSQL al insertar (CHECK, tipos fuera de rango, triggers...): la
  carga debe ir en una transacción y deshacerse entera, indicando la tabla y la fila.
- PENDIENTE 6.3 · Tarea larga: con muchas filas, la inserción debe ir por lotes y en un worker
  asíncrono (según el esquema funcional) para que la WebApp no espere bloqueada.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from .arboles import Arbol
from .orden_arboles import ArbolOrdenado, OrdenArboles
from .prototipo import AUTO, Generador


@dataclass
class EstadoCarga:
    """Estado compartido entre árboles durante la carga."""
    # Filas generadas de cada tabla: la siguiente tupla tendrá id = contador + 1 (paso 6.2).
    # Sirve para calcular a qué FK apuntan los árboles hijo.
    contadores: dict[str, int] = field(default_factory=dict)
    # Raíces de los árboles ya cargados, en orden.
    cargados: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ArbolACargar:
    """Árbol que toca cargar en cada vuelta del bucle exterior."""
    # Posición en el orden de carga (empieza en 1).
    posicion: int
    # Árbol completo con sus nodos
    arbol: Arbol
    # Árbol ordenado con su nivel, los árboles de los que depende y FK que lo causan.
    orden: ArbolOrdenado
    # Referencia a EstadoCarga
    estado: EstadoCarga


def recorrer_arboles(arboles: list[Arbol], orden_carga: OrdenArboles) -> Iterator[ArbolACargar]:
    """Paso 6.1: devuelve los árboles uno a uno en el orden de carga del paso 2.3.

    «Siguiente árbol» (al principio, el primero) → [pasos 6.2 y 6.3] → «¿Último árbol?».
    Cuando se pide el siguiente, el árbol anterior se da por cargado.
    """
    # Ciclo entre árboles
    if not orden_carga.valido:
        raise ValueError("No se pueden recorrer los árboles: el orden de carga tiene errores (ciclo entre árboles)")
    # Diccionario que va de la raíz al árbol.
    por_raiz = {a.raiz: a for a in arboles}
    # Comprobación de que el conjunto de raíces recibidos coincide con el del orden de carga.
    if set(por_raiz) != {o.raiz for o in orden_carga.orden}:
        raise ValueError("Los árboles no coinciden con los del orden de carga")

    # Para cada tabla se crea un contador = 0.
    estado = EstadoCarga(contadores={n.tabla: 0 for a in arboles for n in a.nodos})
    for posicion, ordenado in enumerate(orden_carga.orden, start=1):
        # Garantiza que los árboles de los que depende ya están cargados. Kahn (paso 2.3).
        pendientes = [r for r in ordenado.depende_de if r not in estado.cargados]
        if pendientes:
            raise ValueError(f"El árbol «{ordenado.raiz}» depende de árboles sin cargar: {', '.join(pendientes)}")

        # Quien recibe el árbol genera sus tuplas en profundidad (paso 6.2, generar_tuplas).
        # PENDIENTE 6.3: y las escribe en la BBDD creada en el paso 5.
        yield ArbolACargar(posicion, por_raiz[ordenado.raiz], ordenado, estado) # Se entrega el Arbol a cargar.
        estado.cargados.append(ordenado.raiz) # Cuando se pide el siguiente árbol, el árbol anterior se da por cargado.


@dataclass(frozen=True)
class Tupla:
    """Tupla generada en el paso 6.2."""
    # Nombre de la tabla.
    tabla: str
    # Número de fila desde 0: la tupla tiene id = fila + 1 (el contador de la tabla antes de generarla, + 1).
    fila: int
    # Columnas de la tabla en el orden del DDL y su valor. ``AUTO``: la rellena PostgreSQL (fuera del INSERT).
    columnas: tuple[str, ...]
    valores: tuple

  # ID de la fila
    @property
    def id(self) -> int:
        return self.fila + 1


def generar_tuplas(a_cargar: ArbolACargar, generador: Generador) -> Iterator[Tupla]:
    """Paso 6.2: genera las tuplas de un árbol en profundidad, en el orden del diagrama.

    Por cada tupla de la raíz se generan sus tuplas hijas, por cada hija sus nietas... Cuando una tupla
    no tiene más hijas por construir se sube a la tabla padre y se genera su siguiente tupla.
    Actualiza los contadores del estado de la carga (paso 6.1).
    """
    arbol, contadores = a_cargar.arbol, a_cargar.estado.contadores
    hijas: dict[str, list[str]] = {n.tabla: [] for n in arbol.nodos}
    # Va desde la tabla raíz a cada una de sus tablas hijas.
    for n in arbol.nodos:
        if n.padre:
            hijas[n.padre].append(n.tabla)

    def generar(tabla: str, fila: int) -> Iterator[Tupla]:
        # «Generamos tupla» (id = contador + 1): el reparto en bloques hace que la fila sea el contador, sino esto no se cumple --> ERROR.
        if fila != contadores[tabla]:
            raise RuntimeError(f"La tupla {fila + 1} de «{tabla}» no sigue a su contador ({contadores[tabla]})")
        columnas = tuple(generador.columnas[tabla]) # Tupla con el valor de cada columna.
        yield Tupla(tabla, fila, columnas, tuple(generador.valor(tabla, c, fila) for c in columnas))
        contadores[tabla] += 1
        # «¿La tupla tiene hijos?» → «Generamos tupla en la tabla hija» (y, dentro, sus propias hijas).
        for hija in hijas[tabla]:
            for fila_hija in generador.filas_hijas(hija, fila):
                yield from generar(hija, fila_hija)
        # «¿Quedan tuplas por construir?» No → «¿Existe tabla padre?» Sí: se vuelve a la tupla padre.

  # Genera cada fila de la tabla raíz y, con ella, todo su subárbol.
    for fila in range(generador.filas[arbol.raiz]):
        yield from generar(arbol.raiz, fila)

    # Tuplas huérfanas: si la tabla padre no tiene filas (FK de agrupación nulable), ninguna tupla padre
    # llega a ellas. Se generan al final del árbol, con la FK a NULL.
    for n in arbol.nodos:
        if n.padre and generador.filas[n.padre] == 0:
            for fila in range(generador.filas[n.tabla]):
                yield from generar(n.tabla, fila)

    # «¿Último árbol?»: antes de pasar al siguiente, cada tabla debe tener todas sus filas.
    for n in arbol.nodos:
        # Si no coinciden, o faltan o sabran tuplas.
        if contadores[n.tabla] != generador.filas[n.tabla]:
            raise RuntimeError(f"«{n.tabla}» tiene {contadores[n.tabla]} tuplas generadas de {generador.filas[n.tabla]}")


def generar_carga(arboles: list[Arbol], orden_carga: OrdenArboles, generador: Generador) -> Iterator[Tupla]:
    """Pasos 6.1 y 6.2 juntos: todas las tuplas de la carga, árbol a árbol y en profundidad."""
    for a_cargar in recorrer_arboles(arboles, orden_carga):
        yield from generar_tuplas(a_cargar, generador)
        # PENDIENTE 6.3: escribir las tuplas en la BBDD, tabla a tabla en el orden de Kahn.


__all__ = ["AUTO", "ArbolACargar", "EstadoCarga", "Tupla", "generar_carga", "generar_tuplas", "recorrer_arboles"]
