"""Paso 3 del módulo 1: el usuario define el prototipo de datos.

El único dato que indica el usuario es el número de filas de cada tabla. Los valores no
tienen que ser coherentes con el significado de cada columna: solo respetan su tipo.
Se calculan a partir del número de fila, así que siempre salen iguales y no se repiten
(sirven también para columnas PK y UNIQUE):

    enteros            1, 2, 3...
    numeric/real       1, 2, 3... (dentro de la precisión)
    texto              "AAA", "BBB"... "ZZZ", "AAAB", "BBBB"... (recortado a su longitud)
    boolean            true, false, true...
    fechas y horas     2024-01-01, 2024-01-02...
    uuid               a partir del número de fila

Las columnas IDENTITY, serial, con DEFAULT o generadas las rellena PostgreSQL. Las
columnas FK tomcolumnas FK toman el valor de una fila de la tabla padre: la FK de agrupación reparte las
filas en bloques consecutivos (las primeras hijas para la primera fila del padre, las
siguientes para la segunda...), así que al recorrer el árbol en profundidad (paso 6.2) cada
tabla se genera en orden (id = contador + 1). Las restricciones CHECK no se tienen en cuenta.

Antes de aceptar el prototipo se comprueba que la carga no fallaría ("aviso de
coherencia"): número de filas válido, tipos que se saben generar, FK NOT NULL con
filas en el padre y claves PK/UNIQUE sin valores repetidos.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from pglast import ast, enums
from pglast.stream import RawStream

from .arboles import elegir_fks_agrupacion
from .ddl import ErrorDdl, nombre_tabla
from .dependencias import ClaveForanea, Dependencias

MAX_FILAS = 100_000
FILAS_MUESTRA = 5

_ENTEROS = {"int2": 32_767, "int4": 2_147_483_647, "int8": 9_223_372_036_854_775_807} # Valores máximos de los enteros.
_SERIALES = {"smallserial", "serial2", "serial", "serial4", "bigserial", "serial8"} # Postgre los rellena solo.
_TEXTOS = {"varchar", "bpchar", "text"} # Valores de los textos.
_SOPORTADOS = set(_ENTEROS) | _TEXTOS | {"numeric", "float4", "float8", "bool", "date", "timestamp",
                                         "timestamptz", "time", "uuid"} # Tipos que se saben generar.
_INICIO = datetime(2024, 1, 1) # Fecha de inicio de generación de fechas.
_AUTO = object()  # Marca de valor que genera PostgreSQL, no se sabe que valor tendrá.
# Se usa object para no confundirse con ningún valor real.
AUTO = _AUTO  # Nombre público: en la inserción (paso 6) esas columnas se dejan fuera del INSERT.


@dataclass(frozen=True)
class Columna:
    nombre: str
    tipo: str            # Tal y como se escribe en SQL, p. ej. "varchar(10)".
    base: str            # Nombre interno de pglast, p. ej. "varchar".
    modificadores: tuple[int, ...] # Números entre paréntesis, p. ej. "(10,) o (8, 2) en numeric(8,2)".
    array: bool # ¿Es un array?
    nulable: bool # ¿Admite NULL?
    autogenerada: bool   # IDENTITY, serial, DEFAULT o columna generada.
    generada: bool = False  # GENERATED ALWAYS AS (...) STORED: nunca se puede escribir.


@dataclass(frozen=True)
class TablaPrototipo:
    tabla: str
    filas: int
    columnas: list[Columna]
    # De dónde sale cada columna: "tipo" (según su tipo), "fk" (de la tabla padre) o "auto" (PostgreSQL).
    origenes: list[str] = field(default_factory=list)
    # Primeras filas del prototipo, ya formateadas para mostrarlas ("NULL", "(auto)"...).
    muestra: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class Prototipo:
    tablas: list[TablaPrototipo] = field(default_factory=list) # Lista de tablas.
    errores: list[ErrorDdl] = field(default_factory=list) # Lista de errores.

    @property
    def valido(self) -> bool:
        return not self.errores


# Convierte de pglast a string.
def _nombres(lista) -> tuple[str, ...]:
    return tuple(n.sval for n in lista or ())


def leer_columnas(crear: ast.CreateStmt) -> tuple[list[Columna], list[tuple[str, ...]], tuple[str, ...]]:
    """Recorre los elementos de un CREATE TABLE y devuelve:
    sus columnas, sus claves únicas (PK y UNIQUE, simples o compuestas) y su PK."""
    columnas, claves, no_nulas, pk = [], [], set(), ()
    # Restricciones de tabla.
    for e in crear.tableElts or ():
        if isinstance(e, ast.Constraint):
            if e.contype in (enums.ConstrType.CONSTR_PRIMARY, enums.ConstrType.CONSTR_UNIQUE):
                claves.append(_nombres(e.keys))
                if e.contype == enums.ConstrType.CONSTR_PRIMARY: # La PK es no NULLABLE.
                    pk = _nombres(e.keys)
                    no_nulas.update(pk)
            continue
        # Elementos que no son columnas --> Se saltan.
        if not isinstance(e, ast.ColumnDef):
            continue
        # Restricciones en línea.
        tipos = {c.contype for c in e.constraints or ()}
        if tipos & {enums.ConstrType.CONSTR_PRIMARY, enums.ConstrType.CONSTR_UNIQUE}:
            claves.append((e.colname,))
        if enums.ConstrType.CONSTR_PRIMARY in tipos:
            pk = (e.colname,)
        if tipos & {enums.ConstrType.CONSTR_PRIMARY, enums.ConstrType.CONSTR_NOTNULL}:
            no_nulas.add(e.colname) # PK --> NOT NULL.
        base = e.typeName.names[-1].sval.lower() # Tipo base.
        mods = tuple(m.val.ival for m in e.typeName.typmods or () if isinstance(getattr(m, "val", None), ast.Integer)) # Modificadores.
        autogenerada = base in _SERIALES or e.raw_default is not None or bool(tipos & {
            enums.ConstrType.CONSTR_IDENTITY, enums.ConstrType.CONSTR_DEFAULT, enums.ConstrType.CONSTR_GENERATED}) # Datos Autogenerados.
        tipo = RawStream()(e.typeName).replace("pg_catalog.", "") # Tipo como SQL.
        generada = enums.ConstrType.CONSTR_GENERATED in tipos # Columna calculada por PostgreSQL.
        columnas.append(Columna(e.colname, tipo, base, mods, bool(e.typeName.arrayBounds),
                                True, autogenerada, generada)) # Todas las columnas son nullables
    columnas = [replace(c, nulable=c.nombre not in no_nulas) for c in columnas] # Nulabilidad real.
    return columnas, claves, pk


def _texto(i: int, longitud: int | None) -> str:
    """'AAA', 'BBB'... 'ZZZ', 'AAAB', 'BBBB'...: la letra repetida da i % 26 y el sufijo, i // 26."""
    letra, vuelta = chr(ord("A") + i % 26), i // 26
    sufijo = ""
    while vuelta:
        sufijo = chr(ord("A") + vuelta % 26) + sufijo
        vuelta //= 26
    valor = letra * 3 + sufijo
    return valor[:longitud] if longitud else valor # Se recorte el texto a la longitud del VARCHAR(X).


def valor_por_tipo(columna: Columna, i: int):
    """Valor de la fila ``i`` (desde 0) según el tipo de la columna."""
    n = i + 1
    base, mods = columna.base, columna.modificadores
    if base in _ENTEROS:
        return (n - 1) % _ENTEROS[base] + 1 # 1,2,3... Al pasar del máximo se vuelve a empezar.
    if base in _SERIALES:
        return n
    if base == "numeric":
        if mods:
            precision, escala = mods[0], mods[1] if len(mods) > 1 else 0
            enteros = 10 ** (precision - escala) # Número entero máximo.
            n = n % enteros if enteros > 1 else 0 
            return Decimal(n).quantize(Decimal(1).scaleb(-escala)) # Se le ponen los decimales correspondientes.
        return Decimal(n)
    if base in ("float4", "float8"):
        return float(n)
    if base in _TEXTOS:
        return _texto(i, mods[0] if mods else None)
    if base == "bool":
        return n % 2 == 1 # Alterna empezando por true.
    if base == "date":
        return (_INICIO + timedelta(days=i)).date() # Se suma 1 día cada vez.
    if base in ("timestamp", "timestamptz"):
        return _INICIO + timedelta(days=i) # Se suma 1 día cada vez.
    if base == "time":
        return (datetime.min + timedelta(seconds=i % 86_400)).time() # Se suma 1 segundo cada vez.
    if base == "uuid":
        return f"00000000-0000-4000-8000-{n:012x}" # n en hexadecimal.
    raise ValueError(f"tipo no soportado: {columna.tipo}") # Cualquier otro tipo de dato lanza error.


def _formatear(valor) -> str:
    """Convierte el valor al texto que se muestra."""
    if valor is None:
        return "NULL"
    if valor is _AUTO:
        return "(auto)"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat(sep=" ") if isinstance(valor, datetime) else valor.isoformat()
    return str(valor)


class Generador:
    """Calcula el valor de cualquier columna en cualquier fila, a partir del número de fila."""

    def __init__(self, dependencias: Dependencias, columnas: dict[str, list[Columna]],
                 pks: dict[str, tuple[str, ...]], filas: dict[str, int]):
        """Constructor del generador."""
        self.columnas = {t: {c.nombre: c for c in cols} for t, cols in columnas.items()}
        self.pks = pks
        self.filas = filas
        agrupacion = elegir_fks_agrupacion(dependencias)
        self.fks: dict[str, list[ClaveForanea]] = {}
        for t in columnas:
            propias = [fk for fk in dependencias.claves_foraneas if fk.tabla == t]
            # FK de cada tabla: primero la de agrupación.
            primera = agrupacion.get(t)
            # FK de cada tabla: después el resto en el orden del DDL
            self.fks[t] = ([primera] if primera else []) + [fk for fk in propias if fk != primera]

    def _fila_padre(self, tabla: str, fk: ClaveForanea, i: int) -> int | None:
        """Fila del padre a la que apunta la FK en la fila ``i`` (None si el padre no tiene filas).

        La FK de agrupación (la primera) reparte las filas en bloques consecutivos y equilibrados:
        la fila i va a la fila i * filas_padre // filas de la tabla (con 6 compras y 3 clientes:
        0, 0, 1, 1, 2, 2). Las siguientes usan las cifras de i como un número en base mixta
        (i % filas, luego i // filas...). Dentro de un bloque las combinaciones de FK no se repiten
        mientras haya combinaciones posibles (útil en PK compuestas de FK).
        """
        if fk.autorreferencia:
            return i # La fila se apunta a si misma.
        resto, primera = i, True
        # IMPORTANTE Se recorren las FKs en orden IMPORTANTE.
        for anterior in self.fks[tabla]:
            if anterior.autorreferencia:
                continue
            total = self.filas.get(anterior.tabla_padre, 0)
            # Si el padre está vacío
            if total == 0:
                if anterior is fk:
                    return None
                primera = False # FK con el padre anterior vacío.
                continue
            if anterior is fk:
                # FK de agrupación: bloques. Resto de FK: base mixta.
                return i * total // self.filas[tabla] if primera else resto % total
            if not primera:
                resto //= total
            primera = False # Se deja atras la primera FK.
        return None

    def filas_hijas(self, hija: str, fila_padre: int) -> range:
        """Paso 6.2: filas de ``hija`` que cuelgan de la fila ``fila_padre`` por su FK de agrupación.

        Es el bloque de filas j con j * filas_padre // filas_hija == fila_padre (inverso de _fila_padre).
        """
        agrupacion = next(fk for fk in self.fks[hija] if not fk.autorreferencia)
        hijas, padres = self.filas[hija], self.filas[agrupacion.tabla_padre]
        inicio = -(-fila_padre * hijas // padres) # Redondeo hacia arriba.
        fin = -(-(fila_padre + 1) * hijas // padres)
        return range(inicio, fin) # Es un intervalo de la primera fila a la última

    def valor(self, tabla: str, columna: str, i: int):
        """Calcula el valor de la fila."""
        col = self.columnas[tabla][columna]
        for fk in self.fks[tabla]:
            if columna in fk.columnas:
                if fk.autorreferencia and col.nulable:
                    return None # Autorreferencia y NULLABLE --> Devuelve NULL.
                fila = self._fila_padre(tabla, fk, i) # Busca en la fila del padre y calcula su valor.
                if fila is None:
                    return None
                referenciadas = fk.columnas_padre or self.pks[fk.tabla_padre] # Referencia a la columna indicada o a la PK del padre.
                return self.valor(fk.tabla_padre, referenciadas[fk.columnas.index(columna)], fila) # Copia el valor del padre.
        if col.generada:
            return _AUTO # Columna calculada: la escribe siempre PostgreSQL.
        if col.autogenerada:
            # Los datos seriales tratan de predecirse para las FKs, Los datos DEFAULT no.
            return valor_por_tipo(col, i) if col.base in _ENTEROS or col.base in _SERIALES else _AUTO 
        return valor_por_tipo(col, i)

    def mostrar(self, tabla: str, columna: str, i: int):
        """Como ``valor``, pero las columnas que rellena PostgreSQL se muestran como '(auto)'."""
        col = self.columnas[tabla][columna]
        if col.autogenerada and not any(columna in fk.columnas for fk in self.fks[tabla]):
            return _AUTO
        return self.valor(tabla, columna, i)


def _errores_filas(filas: dict[str, int], orden: list[str]) -> list[ErrorDdl]:
    """Cada tabla del DDL tiene un número de filas entre 0 y MAX_FILAS, y no sobran tablas."""
    # La tabla no está en el DDL.
    errores = [ErrorDdl(f"La tabla «{t}» no está en el DDL") for t in filas if t not in orden]
    for t in orden:
        n = filas.get(t)
        if n is None:
            # La tabla no tiene un número de filas.
            errores.append(ErrorDdl(f"Indica el número de filas de «{t}»"))
        elif not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= MAX_FILAS:
            # El número de filas de X tabla está fuera del intervalo.
            errores.append(ErrorDdl(f"El número de filas de «{t}» debe estar entre 0 y {MAX_FILAS:,}".replace(",", ".")))
    return errores


def _errores_tipos(columnas: dict[str, list[Columna]], dependencias: Dependencias) -> list[ErrorDdl]:
    """Las columnas que hay que rellenar (no FK ni autogeneradas) tienen un tipo que se sabe generar."""
    fk_de = {(fk.tabla, c) for fk in dependencias.claves_foraneas for c in fk.columnas}
    return [ErrorDdl(f"La columna «{t}.{c.nombre}» es de tipo {c.tipo}, que no se puede generar")
            for t, cols in columnas.items() for c in cols
            if (t, c.nombre) not in fk_de and not c.autogenerada and (c.array or c.base not in _SOPORTADOS)]


def _errores_fks(columnas: dict[str, list[Columna]], dependencias: Dependencias,
                 filas: dict[str, int]) -> list[ErrorDdl]:
    """Una tabla con filas no puede tener una FK NOT NULL hacia una tabla sin filas."""
    errores = []
    for fk in dependencias.claves_foraneas:
        if fk.autorreferencia or filas[fk.tabla] == 0 or filas[fk.tabla_padre] > 0:
            continue
        if any(c.nombre in fk.columnas and not c.nulable for c in columnas[fk.tabla]):
            errores.append(ErrorDdl(
                f"«{fk.tabla}» tiene {filas[fk.tabla]} filas, pero su FK NOT NULL ({', '.join(fk.columnas)}) "
                f"apunta a «{fk.tabla_padre}», que tiene 0 filas: dale filas a «{fk.tabla_padre}»"))
    return errores


def _primera_repetida(generador: Generador, tabla: str, clave: tuple[str, ...], filas: int) -> int | None:
    """Primera fila en la que la clave repetiría valores (las filas con NULL no cuentan en UNIQUE)."""
    vistas = set()
    for i in range(filas):
        tupla = tuple(generador.valor(tabla, c, i) for c in clave)
        if any(v is None or v is _AUTO for v in tupla):
            continue
        # Si ya se ha visto una tupla con los mismos valores, se devuelve como primera tupla en la que se repiten valores.
        if tupla in vistas:
            return i
        vistas.add(tupla)
    return None


def _errores_claves(generador: Generador, claves: dict[str, list[tuple[str, ...]]],
                    filas: dict[str, int]) -> list[ErrorDdl]:
    """Las claves PK y UNIQUE no pueden repetir valores."""
    errores = []
    for t, claves_tabla in claves.items():
        for clave in claves_tabla:
            i = _primera_repetida(generador, t, clave, filas[t])
            # Si una una PK o UNQ repetida --> Error.
            if i is not None:
                errores.append(ErrorDdl(
                    f"La clave única ({', '.join(clave)}) de «{t}» repetiría valores a partir de la fila {i + 1}: "
                    f"reduce las filas de «{t}» a {i} como máximo o da más filas a sus tablas padre"))
    return errores


@dataclass(frozen=True)
class Preparacion:
    """Lo que necesitan el prototipo (paso 3) y la inserción (paso 6): el mismo generador para los dos."""
    orden: list[str] = field(default_factory=list)  # Tablas en el orden de Kahn.
    columnas: dict[str, list[Columna]] = field(default_factory=dict) # Columnas de cada tabla.
    generador: Generador | None = None  # None si hay avisos de coherencia.
    errores: list[ErrorDdl] = field(default_factory=list)


def preparar_generador(sentencias: tuple[ast.RawStmt, ...], dependencias: Dependencias,
                       filas: dict[str, int]) -> Preparacion:
    """Lee las columnas de cada tabla, comprueba los avisos de coherencia y crea el generador."""
    # Asocia el nombre de cada tabla con su CREATE TABLE.
    creates = {nombre_tabla(r.stmt.relation): r.stmt for r in sentencias}
    # Lee las columnas en el orden topológico de dependencias.
    orden = [o.tabla for o in dependencias.orden]
    columnas, claves, pks = {}, {}, {}
    for t in orden:
        columnas[t], claves[t], pks[t] = leer_columnas(creates[t])

    # Aviso de coherencia: cada comprobación se hace solo si las anteriores han ido bien.
    errores = _errores_filas(filas, orden) # Número de filas incorrecto.
    if not errores:
        # Tipos que no se saben rellenar o FK apunta hacia tablas vacías.
        errores = _errores_tipos(columnas, dependencias) + _errores_fks(columnas, dependencias, filas)
    if errores:
        return Preparacion(orden, columnas, errores=errores)
    generador = Generador(dependencias, columnas, pks, filas)
    errores = _errores_claves(generador, claves, filas) # Claves repetidas.
    if errores:
        return Preparacion(orden, columnas, errores=errores)
    return Preparacion(orden, columnas, generador)


def generar_prototipo(sentencias: tuple[ast.RawStmt, ...], dependencias: Dependencias,
                      filas: dict[str, int]) -> Prototipo:
    """Comprueba el prototipo (número de filas por tabla) y devuelve una muestra de cada tabla."""
    preparacion = preparar_generador(sentencias, dependencias, filas)
    if not preparacion.generador:
        return Prototipo(errores=preparacion.errores)
    orden, columnas, generador = preparacion.orden, preparacion.columnas, preparacion.generador

    # Se prepara la TablaPrototipo con el origen de cada columna y se muestran sus FILAS_MUESTRA
    fk_de = {(fk.tabla, c) for fk in dependencias.claves_foraneas for c in fk.columnas} # Qué columnas son FK o parte de una FK. (Tabla,Columna)
    tablas = []
    for t in orden:
        nombres = [c.nombre for c in columnas[t]] # Lista de nombres de la columna.
        origenes = ["fk" if (t, c.nombre) in fk_de else "auto" if c.autogenerada else "tipo" for c in columnas[t]] # Cómo se obtiene su valor.
        muestra = [[_formatear(generador.mostrar(t, c, i)) for c in nombres]
                   for i in range(min(filas[t], FILAS_MUESTRA))] # Muestra de FILAS_MUESTRA.
        tablas.append(TablaPrototipo(t, filas[t], columnas[t], origenes, muestra))
    return Prototipo(tablas=tablas)
