"""Paso 6 del módulo 1. 6.1: recorrer los árboles en el orden de carga (bucle exterior de la inserción).
6.2: generar las tuplas de cada árbol en profundidad (bucles interiores)."""

import pytest

from sqlanalyzer_api.plano_datos import (OrdenArboles, analizar_dependencias, formar_arboles, generar_carga,
                                         generar_prototipo, ordenar_arboles, parsear_ddl, preparar_generador,
                                         recorrer_arboles)
from sqlanalyzer_api.plano_datos.insercion import AUTO

TIENDA = """
CREATE TABLE clientes (id int PRIMARY KEY);
CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes(id));
CREATE TABLE lineas_compra (compra_id int REFERENCES compras(id), producto_id int REFERENCES productos(id));
CREATE TABLE productos (id int PRIMARY KEY);
"""


def preparar(ddl):
    resultado = parsear_ddl(ddl)
    dependencias = analizar_dependencias(resultado.sentencias, ddl)
    arboles = formar_arboles(dependencias)
    return arboles, ordenar_arboles(dependencias, arboles, ddl)


def test_los_arboles_salen_en_el_orden_de_carga():
    # lineas_compra (árbol clientes) referencia a productos: el árbol productos se carga antes,
    # aunque en el DDL clientes aparece primero.
    recorrido = list(recorrer_arboles(*preparar(TIENDA)))
    assert [(a.posicion, a.arbol.raiz) for a in recorrido] == [(1, "productos"), (2, "clientes")]
    assert [n.tabla for n in recorrido[1].arbol.nodos] == ["clientes", "compras", "lineas_compra"]
    assert recorrido[1].orden.depende_de == ["productos"]


def test_cada_arbol_se_da_por_cargado_al_pedir_el_siguiente():
    cargados_al_empezar = [list(a.estado.cargados) for a in recorrer_arboles(*preparar(TIENDA))]
    assert cargados_al_empezar == [[], ["productos"]]


def test_hay_un_contador_por_tabla_compartido_entre_arboles():
    recorrido = list(recorrer_arboles(*preparar(TIENDA)))
    assert recorrido[0].estado is recorrido[1].estado
    assert recorrido[0].estado.contadores == {"productos": 0, "clientes": 0, "compras": 0, "lineas_compra": 0}


def test_ultimo_arbol_termina_el_recorrido():
    ddl = "CREATE TABLE a (id int PRIMARY KEY); CREATE TABLE b (id int PRIMARY KEY); CREATE TABLE c (id int);"
    assert [a.arbol.raiz for a in recorrer_arboles(*preparar(ddl))] == ["a", "b", "c"]


def test_con_ciclo_entre_arboles_no_se_recorre():
    with pytest.raises(ValueError, match="ciclo entre árboles"):
        list(recorrer_arboles([], OrdenArboles(errores=["ciclo"])))


def test_arboles_que_no_coinciden_con_el_orden_de_carga():
    arboles, orden = preparar(TIENDA)
    with pytest.raises(ValueError, match="no coinciden"):
        list(recorrer_arboles(arboles[:1], orden))


def test_pendiente_6_3_fk_dentro_del_mismo_arbol_no_la_ordena_la_carga():
    # envios cuelga de compras (FK de agrupación) y también apunta a direcciones; las tres están en
    # el árbol de clientes. El orden de carga solo ordena árboles, y en el preorden del árbol envios va
    # antes que direcciones: si 6.3 insertara siguiendo el preorden, la FK direccion_id fallaría.
    ddl = """
    CREATE TABLE clientes (id int PRIMARY KEY);
    CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes(id));
    CREATE TABLE direcciones (id int PRIMARY KEY, cliente_id int REFERENCES clientes(id));
    CREATE TABLE envios (compra_id int REFERENCES compras(id), direccion_id int REFERENCES direcciones(id));
    """
    [unico] = list(recorrer_arboles(*preparar(ddl)))
    assert unico.orden.referencias == []
    assert [n.tabla for n in unico.arbol.nodos] == ["clientes", "compras", "envios", "direcciones"]


# --- Paso 6.2: tuplas en profundidad ---

def tuplas(ddl, filas):
    resultado = parsear_ddl(ddl)
    dependencias = analizar_dependencias(resultado.sentencias, ddl)
    arboles = formar_arboles(dependencias)
    preparacion = preparar_generador(resultado.sentencias, dependencias, filas)
    assert preparacion.generador, preparacion.errores
    return list(generar_carga(arboles, ordenar_arboles(dependencias, arboles, ddl), preparacion.generador))


def valor(t, columna):
    return t.valores[t.columnas.index(columna)]


PEDIDOS = """
CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(20));
CREATE TABLE compras (id serial PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id));
CREATE TABLE lineas (id serial PRIMARY KEY, compra_id int NOT NULL REFERENCES compras(id));
"""


def test_las_tuplas_siguen_el_orden_del_diagrama():
    # 2 clientes, 2 compras por cliente y 2 líneas por compra: cada tupla va seguida de sus hijas.
    orden = [(t.tabla, t.id) for t in tuplas(PEDIDOS, {"clientes": 2, "compras": 4, "lineas": 8})]
    assert orden == [
        ("clientes", 1),
        ("compras", 1), ("lineas", 1), ("lineas", 2),
        ("compras", 2), ("lineas", 3), ("lineas", 4),
        ("clientes", 2),
        ("compras", 3), ("lineas", 5), ("lineas", 6),
        ("compras", 4), ("lineas", 7), ("lineas", 8),
    ]


def test_cada_hija_apunta_a_la_tupla_padre_que_la_ha_generado():
    padre = {}
    for t in tuplas(PEDIDOS, {"clientes": 3, "compras": 7, "lineas": 10}):
        if t.tabla == "compras":
            assert valor(t, "cliente_id") == padre["clientes"]
        if t.tabla == "lineas":
            assert valor(t, "compra_id") == padre["compras"]
        padre[t.tabla] = valor(t, "id")


def test_id_es_contador_mas_uno():
    generadas = tuplas(PEDIDOS, {"clientes": 3, "compras": 7, "lineas": 10})
    for tabla, total in (("clientes", 3), ("compras", 7), ("lineas", 10)):
        ids = [valor(t, "id") for t in generadas if t.tabla == tabla]
        assert ids == list(range(1, total + 1))


def test_reparto_equilibrado_cuando_no_es_exacto():
    # 7 compras entre 3 clientes: 3, 2 y 2.
    compras = [valor(t, "cliente_id") for t in tuplas(PEDIDOS, {"clientes": 3, "compras": 7, "lineas": 0})
               if t.tabla == "compras"]
    assert compras == [1, 1, 1, 2, 2, 3, 3]


def test_coincide_con_la_vista_previa():
    ddl = """CREATE TABLE clientes (id serial PRIMARY KEY, nombre varchar(100) NOT NULL, activo boolean, alta date);
             CREATE TABLE compras (id int PRIMARY KEY, cliente_id int NOT NULL REFERENCES clientes(id), importe numeric(8,2));"""
    filas = {"clientes": 3, "compras": 6}
    resultado = parsear_ddl(ddl)
    proto = generar_prototipo(resultado.sentencias, analizar_dependencias(resultado.sentencias, ddl), filas)
    muestra = {t.tabla: t.muestra for t in proto.tablas}
    generadas = tuplas(ddl, filas)
    compras = [[str(v) for v in t.valores] for t in generadas if t.tabla == "compras"][:5]
    assert compras == muestra["compras"]
    nombres = [valor(t, "nombre") for t in generadas if t.tabla == "clientes"]
    assert nombres == [f[1] for f in muestra["clientes"]]


def test_el_contador_se_comparte_y_las_fk_a_otro_arbol_apuntan_a_filas_ya_cargadas():
    generadas = tuplas(TIENDA, {"clientes": 2, "compras": 4, "lineas_compra": 4, "productos": 3})
    # El árbol productos va antes: sus 3 tuplas son las primeras.
    assert [t.tabla for t in generadas[:3]] == ["productos"] * 3
    productos = {valor(t, "id") for t in generadas if t.tabla == "productos"}
    assert {valor(t, "producto_id") for t in generadas if t.tabla == "lineas_compra"} <= productos


def test_tuplas_huerfanas_si_el_padre_no_tiene_filas():
    ddl = """CREATE TABLE clientes (id int PRIMARY KEY);
             CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes(id));"""
    generadas = tuplas(ddl, {"clientes": 0, "compras": 3})
    assert [(t.tabla, t.id, valor(t, "cliente_id")) for t in generadas] == [
        ("compras", 1, None), ("compras", 2, None), ("compras", 3, None)]


def test_autorreferencia_nulable_queda_a_null():
    ddl = "CREATE TABLE empleados (id int PRIMARY KEY, jefe_id int REFERENCES empleados(id));"
    assert [valor(t, "jefe_id") for t in tuplas(ddl, {"empleados": 3})] == [None, None, None]


def test_valores_que_rellena_postgresql():
    ddl = """CREATE TABLE t (id serial PRIMARY KEY, n int GENERATED ALWAYS AS IDENTITY,
                             alta timestamp DEFAULT now(), doble int GENERATED ALWAYS AS (id * 2) STORED);"""
    [primera, segunda] = tuplas(ddl, {"t": 2})
    # serial e IDENTITY: id = contador + 1 (para que las FK cuadren); el resto, PostgreSQL.
    assert (valor(segunda, "id"), valor(segunda, "n")) == (2, 2)
    assert valor(primera, "alta") is AUTO
    assert valor(primera, "doble") is AUTO


def test_sin_filas_no_hay_tuplas():
    assert tuplas(PEDIDOS, {"clientes": 0, "compras": 0, "lineas": 0}) == []
