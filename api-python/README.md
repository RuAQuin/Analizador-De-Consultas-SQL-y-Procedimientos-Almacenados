# SQL Analyzer · API Python

API REST (FastAPI) que consume la WebApp Spring Boot. Implementa el Módulo 1
(generación de BBDD) paso a paso según el esquema funcional.

| Paso | Estado |
|------|--------|
| 1. El usuario escribe el DDL y se parsea con pglast | Hecho |
| 2.1. Se leen las FK del DDL y se ordenan las tablas con Kahn | Hecho |
| 2.2. FK de agrupación de cada tabla y formación de los árboles | Hecho |
| 2.3. Kahn entre árboles | Hecho |
| 3. Prototipo de datos (número de filas por tabla) | Hecho |
| 4. Revisión y confirmación | Hecho (junto con el paso 5) |
| 5. CREATE DATABASE / CREATE TABLE | Hecho |
| 6.1. Inserción: recorrer los árboles en orden de carga | Hecho (sin endpoint: lo usarán 6.2 y 6.3) |
| 6.2. Inserción: generar las tuplas de cada árbol en profundidad | Hecho (sin endpoint: lo usará 6.3) |
| 6.3. Inserción: escribir las tuplas en PostgreSQL | Pendiente |
| 7. ANALYZE | Pendiente |
| 8. pg_dump y registro | Pendiente |

## Arrancar

Con Docker (desde la raíz del proyecto):

```bash
docker compose up -d --build --wait   # API en http://localhost:8000, PostgreSQL en localhost:5433
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
| POST | `/bbdd/prototipo` | Paso 3: comprueba el número de filas de cada tabla y devuelve una muestra de los datos |
| POST | `/bbdd/crear` | Pasos 4 y 5: revisa el nombre de la BBDD contra el servidor, la crea y crea sus tablas en el orden de Kahn |

`POST /bbdd/ddl` recibe `{"ddl": "CREATE TABLE ..."}` y siempre responde 200:

```json
{"valido": true, "tablas": ["compras", "clientes"], "errores": [],
 "claves_foraneas": [{"tabla": "compras", "columnas": ["cliente_id"], "tabla_padre": "clientes", "columnas_padre": ["id"]}],
 "orden": [{"tabla": "clientes", "nivel": 0}, {"tabla": "compras", "nivel": 1}],
 "arboles": [{"raiz": "clientes", "nodos": [
   {"tabla": "clientes", "padre": null, "nivel": 0, "fk_agrupacion": null},
   {"tabla": "compras", "padre": "clientes", "nivel": 1, "fk_agrupacion": {"tabla": "compras", "columnas": ["cliente_id"], ...}}]}],
 "orden_carga": [{"raiz": "clientes", "nivel": 0, "depende_de": [], "referencias": []}]}

{"valido": false, "tablas": [], "errores": [{"mensaje": "Error de sintaxis: syntax error at or near \"NUL\"", "linea": 3, "columna": 19}],
 "claves_foraneas": [], "orden": [], "arboles": [], "orden_carga": []}
```

- **Paso 1** (`plano_datos/ddl.py`): solo se admiten sentencias `CREATE TABLE`; cualquier
  otra se devuelve como error indicando su línea.
- **Paso 2.1** (`plano_datos/dependencias.py`): se leen las FK de columna (`REFERENCES`) y
  de tabla (`FOREIGN KEY`). `columnas_padre` vacío significa que se referencia la PK del
  padre. `orden` es el orden topológico de Kahn (padres antes que hijas; a igual nivel,
  el orden del DDL) y `nivel` es el camino más largo desde una tabla sin padres.
  Son errores, porque PostgreSQL no podría crear las tablas solo con `CREATE TABLE`:
  una FK a una tabla no definida, una tabla definida dos veces y un ciclo de FK entre
  tablas (los ciclos no se resuelven: el error lista las FK del ciclo y recomienda
  eliminar una de ellas). Una FK de una
  tabla a sí misma sí se permite y no cuenta para el orden.
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
  a igual nivel, el orden de los árboles). `orden_carga` es la lista de árboles en orden
  de carga con su `nivel`, los árboles de los que dependen (`depende_de`) y las FK que lo
  causan (`referencias`). Aunque las tablas no tengan ciclos, los árboles sí pueden
  formarlos (una tabla de A referencia a B y otra de B a A): en ese caso se devuelve un
  error que nombra los árboles del ciclo y las FK que lo causan, sin intentar resolverlo.
  El error recomienda cambiar el orden de las columnas FK de una tabla (si tiene dos padres
  del mismo nivel, la FK de agrupación es la primera, así que escribir antes la otra la
  cambia de árbol). Solo se proponen los cambios que de verdad rompen el ciclo; si no hay
  ninguno, recomienda eliminar una de las FK que lo causan.

### Prototipo de datos (paso 3)

`POST /bbdd/prototipo` recibe el DDL y el número de filas de cada tabla (el único dato que
indica el usuario). La API no guarda nada entre peticiones, así que vuelve a analizar el
DDL (pasos 1 y 2) y, si es válido, comprueba el prototipo y devuelve una muestra:

```json
{"ddl": "CREATE TABLE ...", "filas": {"clientes": 100, "compras": 300}}

{"valido": true, "errores": [], "tablas": [
  {"tabla": "clientes", "filas": 100,
   "columnas": [{"nombre": "id", "tipo": "serial", "origen": "auto"}, {"nombre": "nombre", "tipo": "varchar(100)", "origen": "tipo"}],
   "muestra": [["(auto)", "AAA"], ["(auto)", "BBB"], ...]}, ...]}
```

`plano_datos/prototipo.py`. Los valores no tienen que ser coherentes: solo respetan el tipo
y se calculan a partir del número de fila, así que no se repiten (sirven para PK y UNIQUE):

| Tipo | Valores |
|------|---------|
| `smallint`, `integer`, `bigint` | 1, 2, 3… |
| `numeric(p,s)`, `real`, `double precision` | 1, 2, 3… dentro de la precisión |
| `varchar(n)`, `char(n)`, `text` | "AAA", "BBB"… "ZZZ", "AAAB", "BBBB"… recortado a `n` |
| `boolean` | true, false, true… |
| `date`, `timestamp`, `time` | 2024-01-01, 2024-01-02… / 00:00:00, 00:00:01… |
| `uuid` | `00000000-0000-4000-8000-000000000001`… |

- `origen` dice de dónde sale cada columna: `tipo` (según su tipo), `fk` (valor de una fila
  de la tabla padre) o `auto` (serial, IDENTITY, DEFAULT o columna generada: la rellena
  PostgreSQL y se muestra como "(auto)").
- La FK de agrupación reparte las filas en bloques consecutivos y equilibrados entre las del
  padre (6 compras y 3 clientes: 1, 1, 2, 2, 3, 3; 7 compras: 1, 1, 1, 2, 2, 3, 3), para que al
  recorrer el árbol en profundidad (paso 6.2) se cumpla `id = contador + 1`. Las demás FK, en base
  mixta para no repetir combinaciones en PK compuestas. Una FK de una tabla a sí misma queda a
  NULL si es nulable.
- La muestra tiene como mucho 5 filas por tabla, en el orden de Kahn de las tablas.
- **Avisos de coherencia** (`valido: false`): falta el número de filas de una tabla, está fuera
  de 0–100.000 o la tabla no existe; un tipo que no se sabe generar (`json`, arrays,
  `interval`…); una FK NOT NULL hacia una tabla con 0 filas; una PK o UNIQUE que repetiría
  valores (se indica a partir de qué fila).
- Las restricciones `CHECK` no se tienen en cuenta.

### Revisión, confirmación y creación (pasos 4 y 5)

En la WebApp, el botón "Confirmar y crear la BBDD" (debajo de la vista previa) llama a
`POST /bbdd/crear`, que recibe lo mismo que `/bbdd/prototipo` más el nombre de la BBDD:

```json
{"nombre": "tienda_demo", "ddl": "CREATE TABLE ...", "filas": {"clientes": 3, "compras": 6}}

{"valido": true, "errores": [], "bbdd": "tienda_demo", "esquemas": [],
 "tablas": [{"tabla": "clientes", "sentencia": "CREATE TABLE clientes (id serial PRIMARY KEY, ...)"},
            {"tabla": "compras", "sentencia": "CREATE TABLE compras (...)"}]}
```

`plano_datos/creacion.py` (con `psycopg`; la conexión sale de las variables `PG_*` de
`docker-compose.yml`, y sin ellas, de `localhost:5433` con `postgres`/`postgres`):

1. Vuelve a comprobar el DDL (pasos 1 y 2) y el prototipo (paso 3): la API no guarda nada.
2. **Revisión (paso 4)**: el nombre debe tener un formato válido, no ser una BBDD reservada
   (`postgres`, `template0`, `template1` ni la del repositorio) y no existir ya en el servidor.
   Si PostgreSQL no responde, también se avisa.
3. **Creación (paso 5)**: `CREATE DATABASE` y, en una sola transacción, `CREATE SCHEMA IF NOT EXISTS`
   de los esquemas del DDL (`ventas.clientes`) y los `CREATE TABLE` en el orden de Kahn. Las
   sentencias las regenera pglast a partir del árbol del paso 1.
4. Si falla algún `CREATE TABLE` (por ejemplo, un `CHECK` sobre una columna que no existe, que
   pglast sí parsea), se deshace la transacción y se borra la BBDD: el error indica la tabla y el
   mensaje de PostgreSQL.

#### Comprobar que la BBDD se ha creado

Las BBDD se crean en el PostgreSQL del contenedor `sqlanalyzer-postgres`, publicado en el puerto
**5433** del host. El 5432 es el PostgreSQL instalado en Windows: es otro servidor y allí no aparecen.

Con `psql` dentro del contenedor (no hace falta instalar nada):

```bash
docker exec -it sqlanalyzer-postgres psql -U postgres -c "\l"                    # BBDD del servidor
docker exec -it sqlanalyzer-postgres psql -U postgres -d tienda_demo -c "\dt"    # tablas de tienda_demo
docker exec -it sqlanalyzer-postgres psql -U postgres -d tienda_demo             # consola interactiva
```

| Comando (en la consola) | Qué muestra |
|-------------------------|-------------|
| `\l` | Todas las BBDD: la creada debe aparecer y una que haya fallado, no |
| `\dt` / `\dt ventas.*` | Tablas del esquema `public` / del esquema `ventas` |
| `\dn` | Esquemas de la BBDD |
| `\d compras` | Columnas, tipos, PK y FK de una tabla |
| `\c otra_bbdd` | Cambiar de BBDD |
| `\q` | Salir |

Las tablas están vacías hasta el paso 6 (inserción de datos): `SELECT count(*) FROM clientes;` da 0.

Con un cliente gráfico (pgAdmin, DBeaver...): host `localhost`, puerto `5433`, usuario y contraseña
`postgres`, BBDD `postgres` (desde ella se ven todas las demás).

Para repetir una prueba con el mismo nombre, se borra la BBDD:

```bash
docker exec -it sqlanalyzer-postgres psql -U postgres -c "DROP DATABASE tienda_demo WITH (FORCE);"
```

### Inserción de datos (paso 6)

`plano_datos/insercion.py` sigue el sub-diagrama «Inserción de datos» en tres pasos:

- **6.1. Recorrer los árboles en orden de carga** (hecho): `recorrer_arboles(arboles, orden_carga)`
  devuelve los árboles uno a uno («Siguiente árbol» … «¿Último árbol?») en el orden del paso 2.3,
  con un `EstadoCarga` compartido: un contador de filas por tabla (para `id = contador + 1`) y los
  árboles ya cargados. Comprueba que los árboles de los que depende cada uno ya se han cargado y no
  recorre nada si hay un ciclo entre árboles.
- **6.2. Generar las tuplas de cada árbol en profundidad** (hecho): `generar_tuplas(arbol_a_cargar,
  generador)` sigue los bucles interiores del diagrama: genera una tupla de la raíz (id = contador + 1),
  después sus tuplas hijas y, bajo cada una, sus nietas; cuando no quedan, sube a la tabla padre y
  genera su siguiente tupla. `generar_carga` une 6.1 y 6.2 (todas las tuplas, árbol a árbol).
  - Usa el mismo `Generador` que la vista previa (`preparar_generador` en `prototipo.py`): lo que se
    genera coincide con lo que el usuario ha confirmado.
  - Las hijas de la fila k del padre son un bloque de filas consecutivas (`Generador.filas_hijas`), así
    que cada tabla se genera en orden y su id es siempre el contador + 1.
  - Tuplas huérfanas: si la tabla padre tiene 0 filas y la FK admite NULL, se generan al final del
    árbol con la FK a NULL.
  - serial e IDENTITY reciben id = contador + 1; un `DEFAULT` que no es un número y las columnas
    `GENERATED ... STORED` quedan como `AUTO` (las rellenará PostgreSQL).
  - Al terminar cada árbol comprueba que cada tabla tiene todas sus filas.
  - Genera las tuplas una a una, sin guardarlas: 300.000 tuplas (100.000 por tabla) en ~1,5 s.
  - Todavía no tiene endpoint: no inserta nada.
- **6.3. Escribir las tuplas en PostgreSQL** (pendiente).

Problemas que habrá que resolver en 6.3 (marcados con `PENDIENTE 6.3` en el código):

| Paso | Problema |
|------|----------|
| 6.3 | El orden de carga solo ordena **entre** árboles. Una FK que no es de agrupación entre dos tablas del mismo árbol (`envios → direcciones`, las dos en el árbol de `clientes`) puede apuntar a una tupla aún no generada. Su valor ya es correcto, pero hay que insertar tabla a tabla en el orden de Kahn (paso 2.1). |
| 6.3 | serial/IDENTITY tienen valor (id = contador + 1): usar `OVERRIDING SYSTEM VALUE` con `GENERATED ALWAYS` y ajustar la secuencia al final (`setval`). |
| 6.3 | Los valores `AUTO` se dejan fuera del `INSERT`. |
| 6.3 | Un `INSERT` puede fallar (`CHECK`, triggers...): una sola transacción que se deshace entera e indica la tabla y la fila. |
| 6.3 | Con muchas filas es una tarea larga: por lotes y en un worker asíncrono. |

Mientras tanto, la BBDD creada en el paso 5 queda con las tablas vacías.

## Tests

```bash
pytest
```

Los tests de `test_creacion.py` que necesitan PostgreSQL se saltan si no está arrancado
(`docker compose up -d`); crean BBDD `test_...` y las borran al terminar.
