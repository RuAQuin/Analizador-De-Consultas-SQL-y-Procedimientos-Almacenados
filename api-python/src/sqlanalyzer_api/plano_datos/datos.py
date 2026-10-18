"""Paso 5 · Generación de los INSERT de datos aleatorios.

Cada tabla se carga con una única sentencia ``INSERT ... SELECT`` sobre
``generate_series``, como en el ejemplo del esquema funcional::

    INSERT INTO b (cliente_id, ..., estado)
    SELECT
        fk1.v[1 + floor(random() * cardinality(fk1.v))::int],
        ...,
        CASE WHEN s.r1 < 0.85 THEN 'ENTREGADO' ... ELSE 'CANCELADO' END
    FROM (SELECT g.i, random() AS r1 FROM generate_series(1, 2000000) AS g(i)) AS s
    CROSS JOIN (SELECT array_agg(id ORDER BY id) ... AS v FROM a) AS fk1;

- ``s.i`` es el número de tupla (1..n): con él se generan los valores de las
  columnas PK/UNQ, que así no se repiten.
- Las columnas con distribución usan un ``random()`` propio calculado en la
  subconsulta (``s.rN``) para que todas las ramas del CASE comparen el mismo número.
- Las columnas FK toman al azar una de las claves ya cargadas en la tabla padre
  (por eso las tablas se cargan de padres a hijas).
"""

from __future__ import annotations

from datetime import date, datetime

from .especificacion import Columna, EspecificacionBbdd, Tabla
from .sql import TipoColumna, analizar_tipo, ident, literal

_FECHA_MINIMA = "0-01-01"
_FECHA_MAXIMA = "2999-12-31"
_LONGITUD_TEXTO_ALEATORIO = 16


# --------------------------------------------------------------------------- límites

def _numero(valor: object, campo: str, nombre: str) -> int | float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"'{nombre}': {campo} debe ser numérico")
    return valor


def _instante(valor: object, campo: str, col: Columna, tipo: TipoColumna) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"'{col.nombre}': {campo} debe ser una fecha ISO (AAAA-MM-DD)")
    try:
        if tipo.familia == "fecha":
            return date.fromisoformat(valor).isoformat()
        return datetime.fromisoformat(valor).isoformat(sep=" ")
    except ValueError:
        raise ValueError(f"'{col.nombre}': {campo} '{valor}' no es una fecha ISO válida") from None


def limites(col: Columna, tipo: TipoColumna) -> tuple[object, object]:
    """Rango [mínimo, máximo] de los valores generados, con valores por defecto según el tipo."""
    familia = tipo.familia
    if familia in ("entero", "decimal", "flotante"):
        if familia == "entero":
            techo = tipo.maximo_entero
            minimo_def, maximo_def = 1, 1000
        elif familia == "decimal":
            precision, escala = tipo.precision_escala
            techo = 10 ** (precision - escala) - 10 ** -escala if precision else None
            minimo_def, maximo_def = 0, min(1000, techo) if techo is not None else 1000
        else:
            techo = None
            minimo_def, maximo_def = 0, 1000
        minimo = _numero(col.minimo, "minimo", col.nombre) if col.minimo is not None else minimo_def
        maximo = _numero(col.maximo, "maximo", col.nombre) if col.maximo is not None else max(maximo_def, minimo)
        if familia == "entero" and (minimo != int(minimo) or maximo != int(maximo)):
            raise ValueError(f"'{col.nombre}': minimo y maximo deben ser enteros")
        if techo is not None and (abs(minimo) > techo or abs(maximo) > techo):
            raise ValueError(f"'{col.nombre}': el rango [{minimo}, {maximo}] no cabe en {tipo.texto}")
    elif familia in ("fecha", "marca_tiempo"):
        minimo = _instante(col.minimo, "minimo", col, tipo) if col.minimo is not None else _FECHA_MINIMA
        maximo = _instante(col.maximo, "maximo", col, tipo) if col.maximo is not None else max(_FECHA_MAXIMA, minimo)
    else:
        if col.minimo is not None or col.maximo is not None:
            raise ValueError(f"'{col.nombre}': minimo/maximo no se aplican al tipo {tipo.texto}")
        return None, None
    if minimo > maximo:
        raise ValueError(f"'{col.nombre}': minimo ({minimo}) mayor que maximo ({maximo})")
    return minimo, maximo


# --------------------------------------------------------------------- expresiones

def expresion_valor(col: Columna, tipo: TipoColumna, tuplas: int) -> str:
    """Expresión SQL que genera el valor de una columna (sin distribución, FK ni nulos).

    Las columnas PK/UNQ se calculan a partir de ``s.i`` para garantizar que no se
    repiten. Lanza ValueError si el tipo/rango no permite ``tuplas`` valores distintos.
    """
    minimo, maximo = limites(col, tipo)
    unica = col.es_unica
    familia = tipo.familia
    t = tipo.texto

    if familia == "entero":
        if unica:
            techo = maximo if col.maximo is not None else tipo.maximo_entero
            if minimo + tuplas - 1 > techo:
                raise ValueError(f"'{col.nombre}': no caben {tuplas} valores únicos a partir de {minimo}")
            return f"(s.i::bigint + {int(minimo) - 1})::{t}"
        return f"({int(minimo)} + floor(random() * {int(maximo) - int(minimo) + 1}))::{t}"

    if familia == "decimal":
        precision, escala = tipo.precision_escala
        if unica:
            if precision and minimo + tuplas - 1 >= 10 ** (precision - escala):
                raise ValueError(f"'{col.nombre}': no caben {tuplas} valores únicos en {t}")
            return f"(s.i + {literal(minimo - 1)})::{t}"
        return f"round(({literal(minimo)} + random() * {literal(maximo - minimo)})::numeric, {escala})"

    if familia == "flotante":
        if unica:
            return f"(s.i + {literal(minimo - 1)})::{t}"
        return f"({literal(minimo)} + random() * {literal(maximo - minimo)})::{t}"

    if familia == "booleano":
        if unica:
            if tuplas > 2:
                raise ValueError(f"'{col.nombre}': un boolean único solo admite 2 tuplas")
            return "(s.i = 1)"
        return "(random() < 0.5)"

    if familia == "fecha":
        inicio = f"DATE {literal(minimo)}"
        if unica:
            if col.maximo is not None and (date.fromisoformat(maximo) - date.fromisoformat(minimo)).days + 1 < tuplas:
                raise ValueError(f"'{col.nombre}': no hay {tuplas} fechas distintas en el rango")
            return f"({inicio} + (s.i - 1))"
        dias = (date.fromisoformat(maximo) - date.fromisoformat(minimo)).days + 1
        return f"({inicio} + floor(random() * {dias})::int)"

    if familia == "marca_tiempo":
        inicio = f"CAST({literal(minimo)} AS {t})"
        if unica:
            return f"({inicio} + (s.i - 1) * INTERVAL '1 second')"
        return f"({inicio} + random() * (CAST({literal(maximo)} AS {t}) - {inicio}))"

    if familia == "texto":
        longitud = tipo.longitud
        if unica:
            prefijo = f"{col.nombre}_"
            cifras = len(str(max(tuplas, 1)))
            if longitud is None or longitud >= len(prefijo) + cifras:
                return f"({literal(prefijo)} || s.i)"
            if longitud >= cifras:
                return "s.i::text"
            raise ValueError(f"'{col.nombre}': {t} es demasiado corto para {tuplas} valores únicos")
        largo = min(longitud or _LONGITUD_TEXTO_ALEATORIO, _LONGITUD_TEXTO_ALEATORIO)
        return f"substr(md5(random()::text), 1, {largo})"

    if familia == "uuid":
        return "gen_random_uuid()"

    raise ValueError(f"'{col.nombre}': tipo {t} sin generador")


def literal_distribucion(valor: object, col: Columna, tipo: TipoColumna) -> str:
    """Literal tipado de un valor de distribución. Lanza ValueError si no encaja en la columna."""
    if valor is None:
        if not col.nulable:
            raise ValueError(f"'{col.nombre}': la distribución incluye NULL pero la columna no es nulable")
        return "NULL"
    familia = tipo.familia
    correcto = {
        "entero": isinstance(valor, int) and not isinstance(valor, bool),
        "decimal": isinstance(valor, (int, float)) and not isinstance(valor, bool),
        "flotante": isinstance(valor, (int, float)) and not isinstance(valor, bool),
        "booleano": isinstance(valor, bool),
    }.get(familia, isinstance(valor, str))
    if not correcto:
        raise ValueError(f"'{col.nombre}': el valor {valor!r} de la distribución no es de tipo {tipo.texto}")
    if familia in ("fecha", "marca_tiempo"):
        valor = _instante(valor, "el valor de la distribución", col, tipo)
    if familia == "texto" and tipo.longitud is not None and len(valor) > tipo.longitud:
        raise ValueError(f"'{col.nombre}': '{valor}' supera la longitud de {tipo.texto}")
    return f"CAST({literal(valor)} AS {tipo.texto})"


def _porcentaje(p: float) -> str:
    return f"{p / 100:.6g}"


# --------------------------------------------------------------------------- INSERT

def insert_aleatorio(espec: EspecificacionBbdd, tabla: Tabla) -> str | None:
    """INSERT ... SELECT que carga ``tabla.tuplas`` tuplas aleatorias (None si no hay que cargar nada)."""
    if tabla.tuplas == 0:
        return None
    aleatorios: list[str] = []      # columnas random() de la subconsulta s
    uniones: list[str] = []         # CROSS JOIN con las claves de las tablas padre
    columnas: list[str] = []
    expresiones: list[str] = []

    def nuevo_aleatorio() -> str:
        aleatorios.append(f"random() AS r{len(aleatorios) + 1}")
        return f"s.r{len(aleatorios)}"

    for col in tabla.columnas:
        if col.identidad:
            continue
        tipo = analizar_tipo(col.tipo)
        destino = espec.destino_fk(col)

        if destino is not None:
            padre, referenciada = destino
            alias = f"fk{len(uniones) + 1}"
            ref = ident(referenciada.nombre)
            uniones.append(
                f"CROSS JOIN (SELECT array_agg({ref} ORDER BY {ref}) FILTER (WHERE {ref} IS NOT NULL) AS v "
                f"FROM {ident(padre.nombre)}) AS {alias}"
            )
            # FK única (relación 1:1): cada hija toma una clave distinta del padre.
            expr = f"{alias}.v[s.i]" if col.es_unica else f"{alias}.v[1 + floor(random() * cardinality({alias}.v))::int]"
        elif col.distribucion:
            r = nuevo_aleatorio()
            ramas, acumulado = [], 0.0
            for i, entrada in enumerate(col.distribucion):
                acumulado += entrada.porcentaje
                valor = literal_distribucion(entrada.valor, col, tipo)
                if i == len(col.distribucion) - 1 and acumulado >= 100 - 1e-9:
                    ramas.append(f"ELSE {valor}")
                else:
                    ramas.append(f"WHEN {r} < {_porcentaje(acumulado)} THEN {valor}")
            if not ramas[-1].startswith("ELSE"):
                # El porcentaje que no cubre la distribución recibe valores aleatorios del tipo.
                ramas.append(f"ELSE {expresion_valor(col, tipo, tabla.tuplas)}")
            expr = "CASE " + " ".join(ramas) + " END"
        else:
            expr = expresion_valor(col, tipo, tabla.tuplas)

        if col.nulable and col.porcentaje_nulos:
            expr = f"CASE WHEN {nuevo_aleatorio()} < {_porcentaje(col.porcentaje_nulos)} THEN NULL ELSE {expr} END"
        columnas.append(ident(col.nombre))
        expresiones.append(expr)

    origen = ", ".join(["g.i", *aleatorios])
    sentencia = [
        f"-- {tabla.nombre}: {tabla.tuplas} tuplas",
        f"INSERT INTO {ident(tabla.nombre)} ({', '.join(columnas)})",
        "SELECT",
        ",\n".join(f"    {e}" for e in expresiones),
        f"FROM (SELECT {origen} FROM generate_series(1, {tabla.tuplas}) AS g(i)) AS s",
        *uniones,
    ]
    return "\n".join(sentencia) + ";"


def sql_carga(espec: EspecificacionBbdd, tabla: Tabla) -> str | None:
    """SQL de carga de una tabla: los INSERT recibidos o, si no hay, la generación aleatoria."""
    if tabla.inserts:
        return tabla.inserts.strip()
    return insert_aleatorio(espec, tabla)
