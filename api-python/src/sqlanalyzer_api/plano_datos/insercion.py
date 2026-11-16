"""Paso 6 del módulo 1: inserción de datos (sub-diagrama «Inserción de datos» del esquema funcional).

Se divide en tres pasos:

- 6.1. Recorrer los árboles en orden de carga (bucle exterior): «Siguiente árbol» … «¿Último árbol?».
  HECHO: ``recorrer_arboles``.
- 6.2. Generar las tuplas de cada árbol en profundidad (bucles interiores): «Generamos tupla»
  (id = contador + 1) → «¿La tupla tiene hijos?» → «Generamos tupla en la tabla hija» → «¿Quedan tuplas
  por construir?» → «¿Existe tabla padre?». HECHO: ``generar_tuplas`` y ``generar_carga``.
- 6.3. Escribir las tuplas en PostgreSQL. HECHO: ``insertar_datos``.

Las tuplas salen del mismo ``Generador`` que la vista previa del paso 3, así que lo insertado coincide con
lo que el usuario ha confirmado. Como la FK de agrupación reparte las hijas en bloques consecutivos,
el recorrido en profundidad genera cada tabla en orden: la tupla de la fila i tiene id = contador + 1.

El 6.3 escribe las tuplas tabla a tabla en el orden de Kahn (paso 2.1), no en el orden en que se generan:
el orden de carga solo ordena los árboles ENTRE sí, y una FK que no es de agrupación entre dos tablas del
mismo árbol (envios → direcciones, las dos en el árbol de clientes) podría apuntar a una tupla aún no
insertada. Los valores no cambian (solo dependen del número de fila) y dentro de cada tabla se mantiene el
orden del diagrama (id 1, 2, 3...).

- Se escribe con COPY (mucho más rápido que un INSERT por fila), que además acepta valores en las columnas
  GENERATED ALWAYS AS IDENTITY (como OVERRIDING SYSTEM VALUE).
- Las columnas ``AUTO`` (DEFAULT que no es un número, GENERATED ... STORED) se dejan fuera: las rellena
  PostgreSQL.
- Al final se ajustan las secuencias de serial/IDENTITY (setval) para que los siguientes INSERT del
  usuario no repitan ids.
- Todo va en una transacción: si una fila falla (CHECK, trigger...) no se inserta nada y el error dice
  la tabla y la fila.
- PENDIENTE: la inserción es síncrona. El esquema funcional prevé workers asíncronos para tareas largas;
  con el límite de 100.000 filas por tabla y COPY tarda segundos, pero con muchas tablas grandes
  convendría pasarla a un worker con progreso.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

import psycopg
from pglast import ast
from psycopg import sql

from .arboles import Arbol
from .creacion import Conexion, revisar_nombre
from .ddl import ErrorDdl
from .dependencias import Dependencias
from .orden_arboles import ArbolOrdenado, OrdenArboles
from .prototipo import AUTO, Generador, preparar_generador


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

        # Quien recibe el árbol genera sus tuplas en profundidad (paso 6.2, generar_tuplas)
        # y el paso 6.3 las escribe en la BBDD creada en el paso 5 (insertar_datos).
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
    # Relaciona cada tabla del árbol con sus hijas.
    for n in arbol.nodos:
        if n.padre:
            hijas[n.padre].append(n.tabla)

    def generar(tabla: str, fila: int) -> Iterator[Tupla]:
        # «Generamos tupla» (id = contador + 1): el reparto en bloques hace que la fila sea el contador, sino esto no se cumple --> ERROR.
        if fila != contadores[tabla]:
            raise RuntimeError(f"La tupla {fila + 1} de «{tabla}» no sigue a su contador ({contadores[tabla]})")
        columnas = tuple(generador.columnas[tabla]) # Tupla con el nombre de cada columna.
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
        # Si no coinciden, o faltan o sobran tuplas.
        if contadores[n.tabla] != generador.filas[n.tabla]:
            raise RuntimeError(f"«{n.tabla}» tiene {contadores[n.tabla]} tuplas generadas de {generador.filas[n.tabla]}")


def generar_carga(arboles: list[Arbol], orden_carga: OrdenArboles, generador: Generador) -> Iterator[Tupla]:
    """Pasos 6.1 y 6.2 juntos: todas las tuplas de la carga, árbol a árbol y en profundidad."""
    for a_cargar in recorrer_arboles(arboles, orden_carga):
        yield from generar_tuplas(a_cargar, generador)


# --- Paso 6.3: escribir las tuplas en PostgreSQL ---

@dataclass(frozen=True)
class Lote:
    """Tuplas de una tabla listas para escribir (COPY), sin las columnas que rellena PostgreSQL."""
    tabla: str
    columnas: tuple[str, ...] # Sin las AUTO.
    filas: list[tuple] = field(default_factory=list) # Tuplas de valores en ese mismo orden.


# Resumen de una tabla escrita (nombre y nº de filas).
@dataclass(frozen=True)
class TablaInsertada:
    tabla: str
    filas: int

# Resultado de la Inserción
@dataclass(frozen=True)
class Insercion:
    bbdd: str | None = None
    # En el orden en que se han escrito (Kahn).
    tablas: list[TablaInsertada] = field(default_factory=list)
    # Segundos que ha tardado.
    segundos: float = 0.0
    # Errores
    errores: list[ErrorDdl] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores


def agrupar_por_tabla(tuplas: Iterable[Tupla], orden: list[str]) -> list[Lote]:
    """Agrupa las tuplas (generadas en profundidad) por tabla, en el orden de Kahn.

    Dentro de cada tabla se mantiene el orden en que se han generado (id 1, 2, 3...).
    Las columnas ``AUTO`` se quitan: son las mismas en todas las tuplas de una tabla.
    """
    columnas: dict[str, tuple[str, ...]] = {} # Nombres.
    posiciones: dict[str, tuple[int, ...]] = {} # No se guardan los valores AUTO.
    filas: dict[str, list[tuple]] = {t: [] for t in orden} # Lista (generada vacía) para cada tabla en orden.
    for t in tuplas:
        # Primera tupla de cada tabla (solo se entra una vez por tabla).
        if t.tabla not in posiciones:
            # Guarda las posiciones de los valores NO AUTO.
            posiciones[t.tabla] = tuple(i for i, v in enumerate(t.valores) if v is not AUTO) 
            # Guarda el nombre de las columnas.
            columnas[t.tabla] = tuple(t.columnas[i] for i in posiciones[t.tabla])
        # Añade cada tupla (Exceptuando las columnas AUTO)
        filas[t.tabla].append(tuple(t.valores[i] for i in posiciones[t.tabla]))
    return [Lote(t, columnas.get(t, ()), filas[t]) for t in orden]


def _identificador(tabla: str) -> sql.Identifier:
    """«ventas.clientes» → "ventas"."clientes"."""
    return sql.Identifier(*tabla.split(".", 1))


class _FalloFila(Exception):
    """Una fila no se ha podido escribir: se guardan la tabla y el error para indicarlos."""

    def __init__(self, tabla: str, error: psycopg.Error):
        super().__init__(tabla)
        self.tabla = tabla
        self.error = error


def _escribir(c: psycopg.Connection, lote: Lote) -> None:
    """Escribe las tuplas de una tabla con COPY (o con sus DEFAULT si todas sus columnas son AUTO)."""
    tabla = _identificador(lote.tabla)
    try:
        if not lote.columnas:
            # Ninguna columna que escribir (TODAS AUTO): cada fila toma los DEFAULT de PostgreSQL.
            c.execute(sql.SQL("INSERT INTO {} SELECT FROM generate_series(1, %s)").format(tabla), (len(lote.filas),))
            return
        # Usamos COPY en lugar de INSERT para que la inserción sea mucho más rápida.
        copia = sql.SQL("COPY {} ({}) FROM STDIN").format(tabla, sql.SQL(", ").join(map(sql.Identifier, lote.columnas)))
        with c.cursor() as cur, cur.copy(copia) as copy:
            for fila in lote.filas:
                copy.write_row(fila) # Escritura de filas.
    # En el momento en el que haya un error, no se inserta ninguna tupla en la tabla (pasado o futura) durante este COMMIT.
    except psycopg.Error as e:
        raise _FalloFila(lote.tabla, e) from e


def _ajustar_secuencias(c: psycopg.Connection, lote: Lote, generador: Generador) -> None:
    """Columnas autogeneradas (serial e IDENTITY): la secuencia sigue al id más alto insertado (si la columna no tiene, no hace nada (devuelve NULL))."""
    for nombre in lote.columnas:
        if not generador.columnas[lote.tabla][nombre].autogenerada:
            continue
        tabla = _identificador(lote.tabla)
        # Se selecciona el max() + 1.
        c.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s, %s), max({})) FROM {}").format(
            sql.Identifier(nombre), tabla), (tabla.as_string(c), nombre))


def _mensaje_fila(e: _FalloFila) -> str:
    """Mensaje de PostgreSQL con la fila que ha fallado (COPY la indica en el contexto: «line N»)."""
    diag = e.error.diag
    linea = re.search(r"line (\d+)", diag.context or "")
    donde = f"la fila {linea.group(1)} de «{e.tabla}»" if linea else f"las filas de «{e.tabla}»"
    mensaje = diag.message_primary or str(e.error).strip().splitlines()[0]
    return f"PostgreSQL no ha podido insertar {donde}: {mensaje}. No se ha insertado ningún dato"


def _tablas_con_filas(c: psycopg.Connection, orden: list[str]) -> list[str]:
    """Devuelve las tablas que ya tienen datos (filas)"""
    return [t for t in orden
            if c.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(_identificador(t))).fetchone()[0]]


def insertar_datos(nombre: str, sentencias: tuple[ast.RawStmt, ...], dependencias: Dependencias,
                   arboles: list[Arbol], orden_carga: OrdenArboles, filas: dict[str, int],
                   conexion: Conexion) -> Insercion:
    """Paso 6 completo: genera las tuplas siguiendo el diagrama (6.1 y 6.2) y las escribe tabla a tabla
    en el orden de Kahn (6.3), en una sola transacción, en la BBDD creada en el paso 5."""
    # Validación del nombre de la BBDD.
    errores = revisar_nombre(nombre, conexion)
    if errores:
        return Insercion(errores=errores)
    # Construcción del Generador a partir del DDL, dependencias y nº de filas. Devuelve también el orden de Kahn.
    preparacion = preparar_generador(sentencias, dependencias, filas)
    if not preparacion.generador:
        return Insercion(errores=preparacion.errores)
    generador = preparacion.generador

    inicio = time.perf_counter() # Hora de inicio.
    # Generación de todas las tuplas y se ordenación por lotes.
    lotes = agrupar_por_tabla(generar_carga(arboles, orden_carga, generador), preparacion.orden)
    try:
        # Una sola transacción: al salir del with se confirma, o se deshace si hay una excepción.
        with conexion.conectar(nombre) as c:
            ocupadas = _tablas_con_filas(c, preparacion.orden)
            # Si alguna tabla ya tiene filas --> No se realiza la inserción.
            if ocupadas:
                return Insercion(errores=[ErrorDdl(
                    f"La tabla «{ocupadas[0]}» de «{nombre}» ya tiene filas: los datos solo se insertan una vez,"
                    " en la base de datos recién creada")])
            # Por cada lote con filas, se escribe y se ajustan secuencias.
            for lote in lotes:
                if lote.filas:
                    _escribir(c, lote)
                    _ajustar_secuencias(c, lote, generador)
    # Mensaje con la Fila y Tabla.
    except _FalloFila as e:
        return Insercion(errores=[ErrorDdl(_mensaje_fila(e))])
    # Fallo de conexión.
    except psycopg.OperationalError as e:
        diag = getattr(e, "diag", None)
        detalle = diag.message_primary if diag and diag.message_primary else str(e).strip().splitlines()[-1]
        return Insercion(errores=[ErrorDdl(f"No se ha podido conectar con la base de datos «{nombre}»: {detalle}")])
    # Error genérico.
    except psycopg.Error as e:
        return Insercion(errores=[ErrorDdl(f"No se han podido insertar los datos: {e.diag.message_primary or e}."
                                           " No se ha insertado ningún dato")])
    # Resultado de la inserción.
    return Insercion(bbdd=nombre, tablas=[TablaInsertada(lo.tabla, len(lo.filas)) for lo in lotes],
                     segundos=round(time.perf_counter() - inicio, 2))


__all__ = ["AUTO", "ArbolACargar", "EstadoCarga", "Insercion", "Lote", "TablaInsertada", "Tupla",
           "agrupar_por_tabla", "generar_carga", "generar_tuplas", "insertar_datos", "recorrer_arboles"]
