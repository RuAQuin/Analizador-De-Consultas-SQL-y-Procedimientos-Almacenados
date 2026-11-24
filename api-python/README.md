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
| 6.1. Inserción: recorrer los árboles en orden de carga | Hecho |
| 6.2. Inserción: generar las tuplas de cada árbol en profundidad | Hecho |
| 6.3. Inserción: escribir las tuplas en PostgreSQL (tabla a tabla en orden de Kahn) | Hecho |
| 7. ANALYZE para cerrar la carga | Hecho |
| 8.1. Respaldo: COPY ... TO PROGRAM 'pg_dump -F c' | Hecho |
| 8.2. Registro de la BBDD objetivo en el repositorio | Hecho |

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
| POST | `/bbdd/insertar` | Paso 6: genera las tuplas siguiendo el diagrama y las escribe tabla a tabla en el orden de Kahn |
| GET | `/bbdd/insertar/progreso/{nombre}` | Paso 6: cómo va la inserción en marcha (reloj de la carga) |
| POST | `/bbdd/analizar` | Paso 7: ANALYZE de cada tabla en el orden de Kahn para cerrar la carga |
| POST | `/bbdd/exportar` | Paso 8: respaldo con COPY ... TO PROGRAM 'pg_dump -F c' y registro como BBDD objetivo |
| GET | `/bbdd/registro` | Paso 8.2: BBDD objetivo registradas, la última primero |
| GET | `/bbdd/dumps/{fichero}` | Paso 8.1: descarga un dump |
| POST | `/bbdd/servidor/probar` | Paso 9: prueba la conexión con el PostgreSQL de otro equipo de la red |
| POST | `/bbdd/restaurar` | Paso 9: restaura el respaldo del paso 8 en el PostgreSQL de otro equipo |

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

Las tablas están vacías hasta el paso 6 (inserción de datos): `SELECT count(*) FROM clientes;` da 0
antes de pulsar "Insertar N filas" y el número de filas indicado después.

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
- **6.3. Escribir las tuplas en PostgreSQL** (hecho): `insertar_datos` y `POST /bbdd/insertar`
  (recibe lo mismo que `/bbdd/crear`). En la WebApp, el botón "Insertar N filas" aparece tras crear la BBDD.
  - Las tuplas se generan con 6.1 y 6.2 (orden del diagrama), se agrupan por tabla y se escriben
    **tabla a tabla en el orden de Kahn** (paso 2.1). El orden de carga solo ordena los árboles entre sí:
    una FK que no es de agrupación entre dos tablas del mismo árbol (`envios → direcciones`, las dos en el
    árbol de `clientes`) fallaría si se insertara en el orden en que se generan. Los valores no cambian y
    dentro de cada tabla se mantiene el orden del diagrama (id 1, 2, 3...).
  - Se escribe con `COPY`, que también acepta valores en `GENERATED ALWAYS AS IDENTITY`. Las columnas
    `AUTO` quedan fuera (si una tabla no tiene ninguna otra, cada fila toma sus `DEFAULT`).
  - Al final se ajustan las secuencias de serial/IDENTITY (`setval`): el siguiente `INSERT` del usuario
    sigue la numeración.
  - Todo va en una transacción: si una fila falla (un `CHECK`, que el prototipo no tiene en cuenta, un
    trigger...) no se inserta nada y el error indica la tabla y la fila. Si alguna tabla ya tiene filas no
    se inserta (los datos se insertan una vez, en la BBDD recién creada).
  - 300.000 filas (100.000 por tabla) tardan ~4,5 s.
  - **Progreso (reloj de la carga):** mientras dura `POST /bbdd/insertar`,
    `GET /bbdd/insertar/progreso/{nombre}` devuelve la fase (`generando` las tuplas o `escribiendo` con
    COPY), la tabla que se escribe y las filas hechas de `total` (se actualiza cada 1.000 filas). Da 404
    si no hay ninguna inserción en marcha en esa BBDD (aún no ha empezado o ya ha terminado). El estado
    está en memoria (`progreso_insercion`): sirve porque la API corre en un solo proceso. La WebApp lo
    consulta cada segundo (`static/js/carga.js`) si la inserción tarda más de 2 s.
  - **Pendiente:** la inserción es síncrona. El esquema funcional prevé workers asíncronos para las tareas
    largas; con el límite de 100.000 filas por tabla basta, pero con muchas tablas grandes convendría
    pasarla a un worker.

```json
{"nombre": "tienda_demo", "ddl": "CREATE TABLE ...", "filas": {"clientes": 3, "compras": 7}}

{"valido": true, "errores": [], "bbdd": "tienda_demo", "segundos": 0.01,
 "tablas": [{"tabla": "clientes", "filas": 3}, {"tabla": "compras", "filas": 7}]}
```

### ANALYZE para cerrar la carga (paso 7)

`analizar_bbdd` (`plano_datos/estadisticas.py`) y `POST /bbdd/analizar`. La petición es igual que la de
`/bbdd/insertar`: el DDL da las tablas y `filas` indica cuántas debería tener cada una.

Hasta que no se analiza una tabla, PostgreSQL no sabe cuántas filas tiene (`pg_class.reltuples` = -1) ni
cómo se reparten sus valores (`pg_stats` vacío). El planificador usaría estimaciones por defecto y los
EXPLAIN del módulo 2 darían planes engañosos.

- Se ejecuta `ANALYZE` tabla a tabla en el orden de Kahn, solo sobre las tablas del DDL.
- Antes se comprueba que los datos estén insertados: si una tabla debería tener filas y está vacía, no
  se analiza nada («inserta antes los datos (paso 6)»).
- De cada tabla se devuelven las filas estimadas antes y después (`reltuples`), las páginas
  (`relpages`) y las columnas con estadísticas (`pg_stats`). Con hasta 30.000 filas (la muestra de
  ANALYZE) la estimación es exacta; con más, sale de una muestra y puede variar un poco.
- ANALYZE no cambia los datos: se puede repetir sin problema.

```json
{"valido": true, "errores": [], "bbdd": "tienda_demo", "segundos": 0.03,
 "tablas": [{"tabla": "clientes", "filas": 1000, "estimadas_antes": -1, "estimadas": 1000, "paginas": 6, "columnas": 3},
            {"tabla": "pedidos", "filas": 50000, "estimadas_antes": -1, "estimadas": 50000, "paginas": 288, "columnas": 3}]}
```

Para comprobarlo en PostgreSQL:

```bash
docker exec -it sqlanalyzer-postgres psql -U postgres -d tienda_demo -c "SELECT relname, reltuples, relpages FROM pg_class WHERE relname IN ('clientes', 'pedidos')"
docker exec -it sqlanalyzer-postgres psql -U postgres -d tienda_demo -c "SELECT tablename, attname, n_distinct FROM pg_stats WHERE schemaname = 'public'"
docker exec -it sqlanalyzer-postgres psql -U postgres -d tienda_demo -c "SELECT relname, last_analyze FROM pg_stat_user_tables"
```

### pg_dump y registro (paso 8)

`exportar_bbdd` (`plano_datos/exportacion.py`) y `POST /bbdd/exportar`, con la misma petición que
`/bbdd/analizar`. Corresponde a «Exportación pg_dump» y «Registro de BBDD objetivo» del plano de datos.

- **Comprobación previa:** la carga debe estar cerrada. Si una tabla con filas no está analizada, no se
  respalda («ejecuta antes ANALYZE (paso 7)»).
- **8.1. Respaldo:** conectados a la BBDD que se respalda, se ejecuta

  ```sql
  COPY (SELECT 1) TO PROGRAM 'pg_dump -U postgres -d <bbdd> -F c -f /datos/dumps/<bbdd>_<AAAAMMDD>_<HHMMSS>.dump';
  ```

  - El programa lo lanza el propio servidor de PostgreSQL: pg_dump es siempre el del servidor (misma
    versión) y la API no necesita instalarlo.
  - Requiere un superusuario o el rol `pg_execute_server_program`.
  - Formato custom (`-F c`): binario y comprimido, con tablas, datos, secuencias, restricciones e
    índices. Se restaura con `pg_restore`.
  - Solo llega a Windows al pulsar el enlace de descarga en la WebApp (se guarda en `Descargas`).
  - Se escribe en `DIRECTORIO_DUMPS_SERVIDOR` (`/datos/dumps` del contenedor de PostgreSQL). Es el volumen
    `dumps`, que la API monta en solo lectura en `DIRECTORIO_DUMPS` para poder descargarlo.
  - El `entrypoint` de PostgreSQL en `docker-compose.yml` da el directorio al usuario `postgres`.
  - `umask 022`: el dump queda legible para la API.
  - Si pg_dump falla, se borra lo que haya escrito: nunca queda un dump a medias.
  - El tamaño se lee con `pg_stat_file`.
- **8.2. Registro:** la BBDD queda apuntada en el repositorio de la aplicación (`sqlanalyzer_repositorio`,
  tabla `bbdd_objetivo`) con su DDL, las filas de cada tabla y su último dump. El módulo 2 podrá elegir entre
  estas BBDD.
  - El repositorio y su tabla se crean la primera vez.
  - Volver a respaldar actualiza el registro.
  - Si el registro falla, se borra el dump.
- `GET /bbdd/registro` lista las BBDD registradas. `existe` indica si siguen en el servidor (se pueden haber
  borrado a mano).
- `GET /bbdd/dumps/{fichero}` descarga un dump. Solo acepta nombres de dump, no rutas. También acepta los
  `.sql` de las exportaciones anteriores (formato script).

```json
{"valido": true, "errores": [], "bbdd": "tienda_demo", "fichero": "tienda_demo_20261121_153642.dump",
 "bytes": 93758, "registrada": "2026-11-21T15:36:42.674274Z", "segundos": 0.13}
```

Para comprobarlo:

```bash
docker exec -it sqlanalyzer-postgres ls -l /datos/dumps                             # dumps generados
docker exec -it sqlanalyzer-postgres pg_restore --list /datos/dumps/tienda_demo_20261121_153642.dump   # contenido
docker exec -it sqlanalyzer-postgres psql -U postgres -d sqlanalyzer_repositorio -c "SELECT nombre, tablas, total_filas, fichero_dump, registrada FROM bbdd_objetivo"
```

Para restaurarlo (`--create` crea la BBDD, así que no debe existir). El dump ya está en el servidor:

```bash
docker exec -it sqlanalyzer-postgres pg_restore -U postgres -d postgres --create /datos/dumps/tienda_demo_20261121_153642.dump
```

### Restaurar en otro servidor (paso 9, opcional)

La BBDD se genera siempre en el servidor de la aplicación (pasos 1 a 8). Para llevarla al PostgreSQL de otro
equipo de la red se aprovecha el respaldo del paso 8 (`plano_datos/restauracion.py`):

- `POST /bbdd/servidor/probar` (`{"host", "puerto", "usuario", "contrasena"}`) comprueba que la API llega al
  servidor y que el usuario puede crear BBDD (`CREATEDB` o superusuario), con una pista si falla
  (contraseña, `pg_hba.conf`, `listen_addresses`, firewall...).
- `POST /bbdd/restaurar` (`{"nombre", "fichero", "servidor"}`):
  1. Solo acepta el `.dump` registrado en el paso 8 para esa BBDD, y la BBDD no debe existir en el otro servidor.
  2. `pg_restore --create --no-owner --no-privileges --exit-on-error` contra el otro servidor
     (`postgresql-client` del repositorio oficial en la imagen de la API; la contraseña va en `PGPASSWORD`).
     `--no-owner --no-privileges`: los objetos pasan a ser del usuario con el que se conecta. Si falla a medias,
     se borra lo restaurado.
  3. `ANALYZE`: el dump no lleva las estadísticas del planificador.
  4. Registro: la copia queda como BBDD objetivo de ese servidor (columna `servidor` = «host:puerto», clave
     `(servidor, nombre)`; vacío = el servidor de la aplicación). Los registros anteriores se adaptan solos.
     «¿Existe?» solo se comprueba en el servidor de la aplicación (`null` en los demás: no se guarda su contraseña).
- La API no guarda la contraseña (la WebApp la tiene solo en la sesión del usuario). «localhost» es el equipo del
  usuario, no el contenedor de la API: se cambia por `HOST_LOCAL` (`host.docker.internal` en `docker-compose.yml`).

En el otro equipo, PostgreSQL debe escuchar en la red (`listen_addresses = '*'`), aceptar al equipo de la API
en `pg_hba.conf`, tener el puerto abierto en el firewall, un usuario con `CREATEDB` y una versión igual o mayor
que la del servidor de la aplicación (17). Para probarlo sin otro equipo,
`docker compose --profile pruebas up -d otro-equipo` arranca un PostgreSQL 17 en el puerto 5434
(`postgres` / `otroequipo`).

## Tests

```bash
pytest
```

Los tests de `test_creacion.py` que necesitan PostgreSQL se saltan si no está arrancado
(`docker compose up -d`); crean BBDD `test_...` y las borran al terminar.
