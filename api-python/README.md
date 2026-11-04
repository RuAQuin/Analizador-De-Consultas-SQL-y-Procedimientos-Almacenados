# SQL Analyzer · API Python

API REST (FastAPI) que consume la WebApp Spring Boot. Implementa el Módulo 1
(generación de BBDD) paso a paso según el esquema funcional.

| Paso | Estado |
|------|--------|
| 1. El usuario escribe el DDL y se parsea con pglast | Hecho |
| 2.1. Se leen las FK del DDL y se ordenan las tablas con Kahn | Hecho |
| 2.2. FK de agrupación de cada tabla y formación de los árboles | Hecho |
| 2.3. Kahn entre árboles | Hecho |
| 3. Prototipo de datos | Pendiente |
| 4. Revisión y confirmación | Pendiente |
| 5. CREATE DATABASE / CREATE TABLE | Pendiente |
| 6. Inserción de datos | Pendiente |
| 7. ANALYZE | Pendiente |
| 8. pg_dump y registro | Pendiente |

## Arrancar

Con Docker (desde la raíz del proyecto):

```bash
docker compose up -d --build --wait   # API en http://localhost:8080, PostgreSQL en localhost:5433
```

En local:

```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .
uvicorn sqlanalyzer_api.app:app --reload
```

## Endpoints

| Método | Ruta | Qué hace |
|--------|------|----------|
| GET | `/salud` | Comprueba que la API está arrancada |
| POST | `/bbdd/ddl` | Paso 1: parsea el DDL con pglast. Paso 2.1: lee las FK y ordena las tablas con Kahn. Paso 2.2: forma los árboles de agrupación. Paso 2.3: ordena los árboles con Kahn |

`POST /bbdd/ddl` recibe `{"ddl": "CREATE TABLE ..."}` y siempre responde 200:

```json
{"valido": true, "tablas": ["compras", "clientes"], "errores": [],
 "claves_foraneas": [{"tabla": "compras", "columnas": ["cliente_id"], "tabla_padre": "clientes", "columnas_padre": ["id"]}],
 "orden": [{"tabla": "clientes", "nivel": 0}, {"tabla": "compras", "nivel": 1}],
 "tablas_intermedias": [], "ddl_final": "CREATE TABLE compras (...); CREATE TABLE clientes (...);",
 "arboles": [{"raiz": "clientes", "nodos": [
   {"tabla": "clientes", "padre": null, "nivel": 0, "fk_agrupacion": null},
   {"tabla": "compras", "padre": "clientes", "nivel": 1, "fk_agrupacion": {"tabla": "compras", "columnas": ["cliente_id"], ...}}]}],
 "orden_carga": [{"arboles": ["clientes"], "nivel": 0, "depende_de": [], "referencias": []}]}

{"valido": false, "tablas": [], "errores": [{"mensaje": "Error de sintaxis: syntax error at or near \"NUL\"", "linea": 3, "columna": 19}],
 "claves_foraneas": [], "orden": [], "tablas_intermedias": [], "ddl_final": null, "arboles": [], "orden_carga": []}
```

- **Paso 1** (`plano_datos/ddl.py`): solo se admiten sentencias `CREATE TABLE`; cualquier
  otra se devuelve como error indicando su línea.
- **Paso 2.1** (`plano_datos/dependencias.py`): se leen las FK de columna (`REFERENCES`) y
  de tabla (`FOREIGN KEY`). `columnas_padre` vacío significa que se referencia la PK del
  padre. `orden` es el orden topológico de Kahn (padres antes que hijas; a igual nivel,
  el orden del DDL) y `nivel` es el camino más largo desde una tabla sin padres.
  Son errores, porque PostgreSQL no podría crear las tablas solo con `CREATE TABLE`:
  una FK a una tabla no definida y una tabla definida dos veces. Una FK de una tabla a
  sí misma sí se permite y no cuenta para el orden.
- **Ciclos de FK** (`plano_datos/ciclos.py`): el sistema los rompe solo. De cada ciclo
  saca una FK a una tabla intermedia `<hija>_<columna sin _id>`, cuya PK es la de la tabla
  hija (sigue habiendo como mucho un valor por fila), y quita esa columna de la hija.
  Se aparta la primera FK del ciclo que apunta a una tabla escrita más abajo en el DDL.
  Una FK no se puede apartar si la hija no tiene PK, si la FK forma parte de la PK, si
  la columna tiene `DEFAULT`/`CHECK` o si se usa en otras restricciones; si ninguna FK
  del ciclo se puede apartar, se devuelve un error. La respuesta incluye
  `tablas_intermedias` y `ddl_final` (el DDL que se usará en adelante; las tablas que no
  cambian conservan el texto del usuario).
- **Paso 2.2** (`plano_datos/arboles.py`): la FK de agrupación de cada tabla es la que
  apunta al padre de nivel más alto (en empate, la primera del DDL; las autorreferencias
  no cuentan). Las tablas sin padres son raíces y cada tabla cuelga de su FK de
  agrupación, así que pertenece a un único árbol. `arboles` sigue el orden de Kahn y sus
  `nodos` van en preorden (cada tabla antes que las que cuelgan de ella). La profundidad
  de una tabla en su árbol coincide con su nivel de Kahn. Las demás FK se resolverán al
  insertar los datos y servirán para ordenar los árboles entre sí (paso 2.3).
- **Paso 2.3** (`plano_datos/orden_arboles.py`): las FK que no son de agrupación y van
  de una tabla de un árbol a una tabla de otro árbol obligan a cargar antes este último.
  Con esas aristas se aplica Kahn entre árboles (la misma función `kahn` del paso 2.1;
  a igual nivel, el orden de los árboles). `orden_carga` es la lista de grupos de carga
  con su `nivel`, los árboles de los que dependen (`depende_de`) y las FK que lo causan
  (`referencias`). Aunque las tablas no tengan ciclos, los árboles sí pueden formarlos
  (una tabla de A referencia a B y otra de B a A); esos árboles se juntan en un mismo
  grupo y se cargarán juntos respetando el orden de Kahn de las tablas. Lo normal es que
  cada grupo tenga un solo árbol.

## Tests

```bash
pytest
```
