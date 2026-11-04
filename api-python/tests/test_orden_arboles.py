"""Paso 2.3 del módulo 1: Kahn entre árboles para decidir cuál se carga primero."""

from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app
from sqlanalyzer_api.plano_datos import (analizar_dependencias, formar_arboles, kahn, ordenar_arboles,
                                         parsear_ddl)


def orden_carga(ddl: str):
    resultado = parsear_ddl(ddl)
    assert resultado.valido, resultado.errores
    dep = analizar_dependencias(resultado.sentencias, ddl)
    assert dep.valido, dep.errores
    return ordenar_arboles(dep, formar_arboles(dep))


def resumen(ddl: str) -> list[tuple[list[str], int, list[str]]]:
    return [(g.arboles, g.nivel, g.depende_de) for g in orden_carga(ddl)]


def test_kahn_generico():
    orden, restantes = kahn(["c", "a", "b"], {("a", "b"), ("b", "c")})
    assert orden == [("a", 0), ("b", 1), ("c", 2)]
    assert restantes == []
    orden, restantes = kahn(["x", "y", "z"], {("x", "y"), ("y", "x")})
    assert orden == [("z", 0)]
    assert restantes == ["x", "y"]


def test_un_arbol_que_referencia_a_otro_se_carga_despues():
    # lineas_compra (árbol clientes) referencia a productos: productos va antes,
    # aunque en el DDL (y en los árboles del paso 2.2) clientes aparece primero.
    ddl = """
        CREATE TABLE clientes (id int PRIMARY KEY);
        CREATE TABLE productos (id int PRIMARY KEY);
        CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes);
        CREATE TABLE lineas_compra (compra_id int REFERENCES compras, producto_id int REFERENCES productos);
    """
    grupos = orden_carga(ddl)
    assert [(g.arboles, g.nivel, g.depende_de) for g in grupos] == [
        (["productos"], 0, []), (["clientes"], 1, ["productos"])]
    [fk] = grupos[1].referencias
    assert (fk.tabla, fk.columnas, fk.tabla_padre) == ("lineas_compra", ("producto_id",), "productos")


def test_arboles_independientes_mantienen_el_orden():
    assert resumen("CREATE TABLE a (id int); CREATE TABLE b (id int);") == [(["a"], 0, []), (["b"], 0, [])]


def test_la_tabla_que_crea_la_dependencia_puede_estar_en_lo_profundo_del_arbol():
    # Árbol monedas: monedas <- tarifas <- envios_tipo <- stock. Árbol almacenes: solo almacenes.
    ddl = """
        CREATE TABLE envios_tipo (id int PRIMARY KEY, tarifa_id int REFERENCES tarifas);
        CREATE TABLE tarifas (id int PRIMARY KEY, moneda char(3) REFERENCES monedas);
        CREATE TABLE monedas (codigo char(3) PRIMARY KEY);
        CREATE TABLE almacenes (id int PRIMARY KEY);
        CREATE TABLE stock (almacen_id int REFERENCES almacenes, tipo_id int REFERENCES envios_tipo);
    """
    # stock cuelga de envios_tipo (nivel 2) y referencia a almacenes; todo lo demás es un único árbol (monedas).
    assert resumen(ddl) == [(["almacenes"], 0, []), (["monedas"], 1, ["almacenes"])]


def test_dependencias_de_varios_arboles_y_niveles():
    ddl = """
        CREATE TABLE a (id int PRIMARY KEY);
        CREATE TABLE b (id int PRIMARY KEY);
        CREATE TABLE c (id int PRIMARY KEY);
        CREATE TABLE c_hija (c_id int REFERENCES c, b_id int REFERENCES b);
        CREATE TABLE b_hija (b_id int REFERENCES b, a_id int REFERENCES a);
    """
    # b_hija cuelga de b y referencia a; c_hija cuelga de c y referencia b: a -> b -> c.
    assert resumen(ddl) == [(["a"], 0, []), (["b"], 1, ["a"]), (["c"], 2, ["b"])]


def test_referencias_dentro_del_mismo_arbol_no_cuentan():
    ddl = """
        CREATE TABLE clientes (id int PRIMARY KEY);
        CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes);
        CREATE TABLE devoluciones (compra_id int REFERENCES compras, cliente_id int REFERENCES clientes);
    """
    assert resumen(ddl) == [(["clientes"], 0, [])]


def test_autorreferencias_no_cuentan():
    ddl = "CREATE TABLE empleados (id int PRIMARY KEY, jefe_id int REFERENCES empleados);"
    assert resumen(ddl) == [(["empleados"], 0, [])]


def test_arboles_en_ciclo_forman_un_grupo():
    # a2 cuelga de a1 y referencia b1; b2 cuelga de b1 y referencia a1: A y B se necesitan mutuamente.
    ddl = """
        CREATE TABLE a1 (id int PRIMARY KEY);
        CREATE TABLE b1 (id int PRIMARY KEY);
        CREATE TABLE c1 (id int PRIMARY KEY);
        CREATE TABLE a2 (a1_id int REFERENCES a1, b1_id int REFERENCES b1);
        CREATE TABLE b2 (b1_id int REFERENCES b1, a1_id int REFERENCES a1);
        CREATE TABLE c2 (c1_id int REFERENCES c1, a1_id int REFERENCES a1);
    """
    grupos = orden_carga(ddl)
    assert [(g.arboles, g.nivel, g.depende_de) for g in grupos] == [
        (["a1", "b1"], 0, []), (["c1"], 1, ["a1"])]
    # Las referencias internas del grupo no se listan como dependencias.
    assert grupos[0].referencias == []


cliente = TestClient(app)


def test_endpoint_devuelve_el_orden_de_carga():
    ddl = """
        CREATE TABLE clientes (id int PRIMARY KEY);
        CREATE TABLE productos (id int PRIMARY KEY);
        CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes, producto_id int REFERENCES productos);
    """
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": ddl}).json()
    # compras cuelga de clientes (primera FK en el empate) y referencia a productos.
    assert cuerpo["orden_carga"] == [
        {"arboles": ["productos"], "nivel": 0, "depende_de": [], "referencias": []},
        {"arboles": ["clientes"], "nivel": 1, "depende_de": ["productos"], "referencias": [
            {"tabla": "compras", "columnas": ["producto_id"], "tabla_padre": "productos", "columnas_padre": []}]},
    ]


def test_endpoint_ddl_invalido_no_tiene_orden_de_carga():
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": "CREATE TABLA a (id int);"}).json()
    assert cuerpo["orden_carga"] == []
