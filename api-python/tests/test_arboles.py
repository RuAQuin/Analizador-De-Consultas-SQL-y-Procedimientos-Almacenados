"""Paso 2.2 del módulo 1: FK de agrupación de cada tabla y formación de los árboles."""

from fastapi.testclient import TestClient

from sqlanalyzer_api.app import app
from sqlanalyzer_api.plano_datos import analizar_dependencias, elegir_fks_agrupacion, formar_arboles, parsear_ddl

TIENDA = """
CREATE TABLE lineas_compra (
  compra_id bigint REFERENCES compras(id),
  num_linea integer,
  producto_id integer REFERENCES productos(id),
  PRIMARY KEY (compra_id, num_linea)
);
CREATE TABLE compras (id bigint PRIMARY KEY, cliente_id integer NOT NULL REFERENCES clientes);
CREATE TABLE productos (id integer PRIMARY KEY);
CREATE TABLE clientes (id integer PRIMARY KEY);
"""


def dependencias(ddl: str):
    resultado = parsear_ddl(ddl)
    assert resultado.valido, resultado.errores
    dep = analizar_dependencias(resultado.sentencias, ddl)
    assert dep.valido, dep.errores
    return dep


def agrupacion(ddl: str) -> dict[str, tuple[str, ...] | None]:
    """Tabla -> columnas de su FK de agrupación (None en las raíces)."""
    return {t: fk.columnas if fk else None for t, fk in elegir_fks_agrupacion(dependencias(ddl)).items()}


def estructura(ddl: str) -> list[list[tuple[str, str | None]]]:
    """Cada árbol como lista (tabla, padre) en preorden."""
    return [[(n.tabla, n.padre) for n in a.nodos] for a in formar_arboles(dependencias(ddl))]


def test_se_elige_el_padre_de_nivel_mas_alto():
    # lineas_compra apunta a compras (nivel 1) y a productos (nivel 0): agrupa por compras.
    assert agrupacion(TIENDA) == {"productos": None, "clientes": None,
                                  "compras": ("cliente_id",), "lineas_compra": ("compra_id",)}


def test_arboles_de_la_tienda():
    # productos queda como árbol aparte: lineas_compra cuelga de compras.
    assert estructura(TIENDA) == [
        [("productos", None)],
        [("clientes", None), ("compras", "clientes"), ("lineas_compra", "compras")],
    ]


def test_la_profundidad_en_el_arbol_coincide_con_el_nivel():
    ddl = """
        CREATE TABLE a (id int PRIMARY KEY);
        CREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);
        CREATE TABLE c (id int PRIMARY KEY, b_id int REFERENCES b);
        CREATE TABLE d (a_id int REFERENCES a, c_id int REFERENCES c);
    """
    # d apunta a a (nivel 0) y a c (nivel 2): cuelga de c, a profundidad 3.
    [arbol] = formar_arboles(dependencias(ddl))
    assert [(n.tabla, n.padre, n.nivel) for n in arbol.nodos] == [
        ("a", None, 0), ("b", "a", 1), ("c", "b", 2), ("d", "c", 3)]


def test_empate_de_nivel_gana_la_primera_fk_del_ddl():
    ddl = """
        CREATE TABLE x (id int PRIMARY KEY);
        CREATE TABLE y (id int PRIMARY KEY);
        CREATE TABLE z (y_id int REFERENCES y, x_id int REFERENCES x);
    """
    assert agrupacion(ddl)["z"] == ("y_id",)
    assert estructura(ddl) == [[("x", None)], [("y", None), ("z", "y")]]


def test_dos_fk_al_mismo_padre_gana_la_primera():
    ddl = """
        CREATE TABLE personas (id int PRIMARY KEY);
        CREATE TABLE mensajes (emisor int REFERENCES personas, receptor int REFERENCES personas);
    """
    assert agrupacion(ddl)["mensajes"] == ("emisor",)


def test_autorreferencia_no_es_fk_de_agrupacion():
    ddl = """
        CREATE TABLE departamentos (id int PRIMARY KEY);
        CREATE TABLE empleados (id int PRIMARY KEY, jefe_id int REFERENCES empleados,
                                departamento_id int REFERENCES departamentos);
        CREATE TABLE socios (id int PRIMARY KEY, padrino_id int REFERENCES socios);
    """
    assert agrupacion(ddl) == {"departamentos": None, "socios": None, "empleados": ("departamento_id",)}
    assert estructura(ddl) == [[("departamentos", None), ("empleados", "departamentos")], [("socios", None)]]


def test_varias_hijas_siguen_el_orden_de_kahn():
    ddl = """
        CREATE TABLE clientes (id int PRIMARY KEY);
        CREATE TABLE direcciones (cliente_id int REFERENCES clientes);
        CREATE TABLE compras (id int PRIMARY KEY, cliente_id int REFERENCES clientes);
        CREATE TABLE lineas (compra_id int REFERENCES compras);
        CREATE TABLE telefonos (cliente_id int REFERENCES clientes);
    """
    # Preorden: cada hija va seguida de su subárbol antes de pasar a la siguiente hija.
    assert estructura(ddl) == [[("clientes", None), ("direcciones", "clientes"), ("compras", "clientes"),
                                ("lineas", "compras"), ("telefonos", "clientes")]]


def test_tablas_sin_fk_son_un_arbol_cada_una():
    assert estructura("CREATE TABLE a (id int); CREATE TABLE b (id int);") == [[("a", None)], [("b", None)]]


cliente = TestClient(app)


def test_endpoint_devuelve_los_arboles():
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": TIENDA}).json()
    assert cuerpo["valido"] is True
    assert [a["raiz"] for a in cuerpo["arboles"]] == ["productos", "clientes"]
    nodos = cuerpo["arboles"][1]["nodos"]
    assert nodos[0] == {"tabla": "clientes", "padre": None, "nivel": 0, "fk_agrupacion": None}
    assert nodos[2] == {"tabla": "lineas_compra", "padre": "compras", "nivel": 2, "fk_agrupacion": {
        "tabla": "lineas_compra", "columnas": ["compra_id"], "tabla_padre": "compras", "columnas_padre": ["id"]}}


def test_endpoint_ciclo_entre_tablas_es_error_y_no_tiene_arboles():
    ddl = """CREATE TABLE departamentos (id integer PRIMARY KEY, responsable_id integer REFERENCES empleados(id));
             CREATE TABLE empleados (id integer PRIMARY KEY, departamento_id integer REFERENCES departamentos(id));"""
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": ddl}).json()
    assert cuerpo["valido"] is False
    assert "ciclo de FK" in cuerpo["errores"][0]["mensaje"]
    assert cuerpo["arboles"] == []


def test_endpoint_ddl_invalido_no_tiene_arboles():
    cuerpo = cliente.post("/bbdd/ddl", json={"ddl": "CREATE TABLE a (b_id int REFERENCES b);"}).json()
    assert cuerpo["arboles"] == []
