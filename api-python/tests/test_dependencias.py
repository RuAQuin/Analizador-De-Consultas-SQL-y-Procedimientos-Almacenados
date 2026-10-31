"""Paso 2.1 del módulo 1: lectura de las FK del DDL y orden topológico de Kahn."""

from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app
from sqlanalyzer_api.plano_datos import ClaveForanea, TablaOrdenada, analizar_dependencias, parsear_ddl


def analizar(ddl: str):
    resultado = parsear_ddl(ddl)
    assert resultado.valido, resultado.errores
    return analizar_dependencias(resultado.sentencias, ddl)


def niveles(dependencias) -> list[tuple[str, int]]:
    return [(o.tabla, o.nivel) for o in dependencias.orden]


def test_lee_fk_de_columna_y_de_tabla():
    dep = analizar("""
        CREATE TABLE a (id int PRIMARY KEY);
        CREATE TABLE c (k1 int, k2 int, PRIMARY KEY (k1, k2));
        CREATE TABLE b (
            id int PRIMARY KEY,
            a_id int REFERENCES a,
            x int, y int,
            CONSTRAINT fk_c FOREIGN KEY (x, y) REFERENCES c (k1, k2)
        );
    """)
    assert dep.claves_foraneas == [
        ClaveForanea("b", ("a_id",), "a", ()),
        ClaveForanea("b", ("x", "y"), "c", ("k1", "k2")),
    ]


def test_padres_antes_que_hijas_aunque_el_ddl_venga_desordenado():
    # Las hijas se escriben antes que sus padres: Kahn las reordena.
    dep = analizar("""
        CREATE TABLE lineas (compra_id int REFERENCES compras(id), producto_id int REFERENCES productos(id));
        CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes(id));
        CREATE TABLE productos (id int PRIMARY KEY);
        CREATE TABLE clientes (id int PRIMARY KEY);
    """)
    assert dep.valido
    assert niveles(dep) == [("productos", 0), ("clientes", 0), ("compras", 1), ("lineas", 2)]


def test_el_nivel_es_el_camino_mas_largo_desde_una_raiz():
    # d cuelga de a (nivel 0) y de c (nivel 2): su nivel es 3, no 1.
    dep = analizar("""
        CREATE TABLE a (id int PRIMARY KEY);
        CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);
        CREATE TABLE c (id int PRIMARY KEY, b_id int REFERENCES b);
        CREATE TABLE d (a_id int REFERENCES a, c_id int REFERENCES c);
    """)
    assert niveles(dep) == [("a", 0), ("b", 1), ("c", 2), ("d", 3)]


def test_tablas_sin_fk_son_todas_nivel_0_en_el_orden_del_ddl():
    dep = analizar("CREATE TABLE z (id int); CREATE TABLE a (id int); CREATE TABLE m (id int);")
    assert niveles(dep) == [("z", 0), ("a", 0), ("m", 0)]


def test_varias_fk_a_la_misma_tabla_cuentan_una_vez():
    dep = analizar("""
        CREATE TABLE personas (id int PRIMARY KEY);
        CREATE TABLE mensajes (emisor int REFERENCES personas, receptor int REFERENCES personas);
    """)
    assert len(dep.claves_foraneas) == 2
    assert niveles(dep) == [("personas", 0), ("mensajes", 1)]


def test_autorreferencia_no_afecta_al_orden():
    dep = analizar("""
        CREATE TABLE empleados (id int PRIMARY KEY, jefe_id int REFERENCES empleados(id));
    """)
    assert dep.valido
    assert dep.claves_foraneas[0].autorreferencia
    assert niveles(dep) == [("empleados", 0)]


def test_fk_a_tabla_no_definida():
    ddl = "CREATE TABLE compras (\n  id int PRIMARY KEY,\n  cliente_id int REFERENCES clientes(id)\n);"
    dep = analizar(ddl)
    assert not dep.valido
    [error] = dep.errores
    assert "«clientes»" in error.mensaje and "no está definida" in error.mensaje
    assert error.linea == 3
    assert dep.orden == []


def test_ciclo_entre_tablas():
    dep = analizar("""
        CREATE TABLE raiz (id int PRIMARY KEY);
        CREATE TABLE a (id int PRIMARY KEY, b_id int REFERENCES b);
        CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);
        CREATE TABLE cuelga (a_id int REFERENCES a);
    """)
    assert not dep.valido
    [error] = dep.errores
    # «cuelga» no forma parte del ciclo, aunque Kahn tampoco pueda ordenarla.
    assert "«a», «b»" in error.mensaje and "cuelga" not in error.mensaje


def test_tabla_definida_dos_veces():
    dep = analizar("CREATE TABLE a (id int);\nCREATE TABLE a (id int);")
    assert not dep.valido
    assert "más de una vez" in dep.errores[0].mensaje


def test_tablas_con_esquema():
    dep = analizar("""
        CREATE TABLE ventas.clientes (id int PRIMARY KEY);
        CREATE TABLE ventas.pedidos (id int, cliente_id int REFERENCES ventas.clientes);
    """)
    assert dep.orden == [TablaOrdenada("ventas.clientes", 0), TablaOrdenada("ventas.pedidos", 1)]


cliente = TestClient(app)


def test_endpoint_devuelve_fk_y_orden():
    ddl = """
        CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes(id));
        CREATE TABLE clientes (id int PRIMARY KEY);
    """
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": ddl}).json()
    assert cuerpo["valido"] is True
    assert cuerpo["tablas"] == ["compras", "clientes"]
    assert cuerpo["claves_foraneas"] == [
        {"tabla": "compras", "columnas": ["cliente_id"], "tabla_padre": "clientes", "columnas_padre": ["id"]}]
    assert cuerpo["orden"] == [{"tabla": "clientes", "nivel": 0}, {"tabla": "compras", "nivel": 1}]


def test_endpoint_fk_rota_no_es_valido():
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": "CREATE TABLE a (b_id int REFERENCES b);"}).json()
    assert cuerpo["valido"] is False
    assert cuerpo["orden"] == []
    assert "«b»" in cuerpo["errores"][0]["mensaje"]
