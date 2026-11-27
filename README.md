# SQL Analyzer

Analizador de consultas SQL y procedimientos almacenados (TFG, Grado en Ingeniería Informática, Universidad de
Burgos). Tiene tres módulos:

| Módulo | Qué hace | Estado |
|--------|----------|--------|
| 1. Generación de BBDD | A partir de un DDL y del número de filas de cada tabla, crea la BBDD en PostgreSQL, la llena de datos, la analiza (ANALYZE), la exporta con `pg_dump` y la registra como BBDD objetivo. Opcionalmente, la restaura en el PostgreSQL de otro equipo | Hecho |
| 2. Análisis de consultas | Análisis estático con pglast, EXPLAIN, formato SQL y recomendaciones | Pendiente (solo el formulario) |
| 3. Logs JPA/Hibernate | Cargar un `.txt` de logs, extraer las consultas y analizarlas | Pendiente (solo la subida del fichero) |

## Arquitectura

```
Navegador ──► WebApp (Spring Boot, :8080) ──REST──► API Python (FastAPI, :8000) ──► PostgreSQL (:5433)
               usuarios, roles y pantallas          parseo, generación de datos,      BBDD objetivo, dumps y
               (BBDD propia H2)                     pg_dump / pg_restore              repositorio de BBDD objetivo
```

- **La WebApp nunca se conecta a las BBDD**: solo muestra y llama a la API (`app.api.url`, variable `API_URL`).
- **La API no guarda nada entre peticiones**: la WebApp le envía en cada paso el DDL y las filas que tiene en la
  sesión del usuario.
- La API y PostgreSQL corren en Docker (`docker-compose.yml`) y solo se publican en `127.0.0.1`: la API no tiene
  login, así que los roles de la WebApp no se pueden saltar por ella.

La API (endpoints, pasos del módulo 1 y sus tests) se documenta en [`api-python/README.md`](api-python/README.md).

## Arrancar

Requisitos: Docker Desktop, Java 21 y Maven.

1. **API y PostgreSQL** (desde esta carpeta):
   ```bash
   docker compose up -d --build --wait
   ```
2. **WebApp**:
   ```bash
   mvn spring-boot:run
   # o
   mvn package && java -jar target/sqlanalyzer-webapp-0.1.0.jar
   ```
3. Abrir http://localhost:8080 y entrar con uno de los usuarios iniciales (ver abajo).

Para parar: `docker compose down` (se conservan BBDD y dumps) o `docker compose down -v` (se borran).

## Configuración de la WebApp

En `src/main/resources/application.properties`:

| Propiedad | Por defecto | Qué es |
|-----------|-------------|--------|
| `app.api.url` (variable `API_URL`) | `http://localhost:8000` | Dirección de la API Python |
| `app.api.timeout` | `10m` | Máximo que se espera la respuesta de la API (la inserción de millones de filas tarda más de 30 s). Si la API está parada se detecta enseguida: la conexión tiene su propio límite de 3 s |
| `server.servlet.session.timeout` | `30m` | Caducidad de la sesión. El progreso del módulo 1 (DDL validado, prototipo, BBDD creada...) se guarda en ella |
| `spring.datasource.url` | `./data/sqlanalyzer` | BBDD propia H2 (usuarios y propietarios de las BBDD) |

## Usuarios y roles

Las cuentas se guardan en la BBDD propia H2 (fichero `./data/sqlanalyzer`, tabla `usuarios`), con Spring Data
JPA. La primera vez que arranca la aplicación (tabla vacía) se crean dos cuentas:

| Usuario    | Contraseña    | Rol     |
|------------|---------------|---------|
| `admin`    | `admin123`    | ADMIN   |
| `analista` | `analista123` | ANALYST |

Son contraseñas de ejemplo. Se cambian con las variables `APP_ADMIN_USER`, `APP_ADMIN_PASSWORD`,
`APP_ANALYST_USER` y `APP_ANALYST_PASSWORD`, que solo tienen efecto con la tabla vacía; después, desde la pantalla
**Usuarios**.

| Rol | Puede |
|-----|-------|
| ADMIN | Todo: todas las BBDD, paso 9 (restaurar en otro servidor), análisis, logs y gestión de usuarios |
| ANALYST | Todas las BBDD, análisis y logs. Sin paso 9 ni gestión de usuarios |
| USUARIO | Solo las BBDD que crea él, análisis y logs. Sin paso 9 ni gestión de usuarios |

- **Registro público** (`/registro`, enlazado desde el login): crea cuentas con rol USUARIO. Los roles ANALYST y
  ADMIN solo los da un administrador.
- **Gestión de usuarios** (`/usuarios`, solo ADMIN): listar, crear, editar (usuario, contraseña opcional, rol,
  habilitado) y eliminar. No se puede eliminar la propia cuenta ni dejar la aplicación sin ningún administrador.
- **Propietario de cada BBDD** (tabla `bbdd_propietarios` de H2): se apunta al crearla en el paso 5. El rol
  USUARIO solo ve en el registro y solo descarga los dumps de sus BBDD. Si se renombra a un usuario, sus BBDD le
  siguen; si se elimina, quedan sin propietario y solo las ven ADMIN y ANALYST.

## Seguridad

- Login por formulario propio (`/login`) contra la BBDD de usuarios; logout por POST que invalida la sesión.
- Contraseñas con BCrypt, nunca en claro ni en los formularios de edición.
- Autorización por rol: `/usuarios/**` y el paso 9 (`/bbdd/servidor/**`, `/bbdd/restaurar`) solo ADMIN;
  `/bbdd/**`, `/analisis/**` y `/logs/**` los tres roles.
- CSRF activo en todos los formularios (incluida la subida de ficheros).
- Cabeceras: Content-Security-Policy sin scripts ni estilos inline, `frame-ancestors 'none'`, Referrer-Policy.
- Cookie de sesión `HttpOnly` y `SameSite=Strict`, caducidad 30 min, protección contra fijación de sesión.
- La contraseña del PostgreSQL de otro equipo (paso 9) solo se guarda en la sesión, nunca en H2.
- Páginas propias de acceso denegado (403) y de error.

## Estructura de la WebApp

```
src/main/java/es/tfg/sqlanalyzer
├── SqlAnalyzerApplication.java
├── api/           ApiPythonClient (único cliente de la API) y los records de sus respuestas
│                  (ValidacionDdl, PrototipoDatos, CreacionBbdd, InsercionDatos, AnalisisBbdd,
│                  ExportacionBbdd, RestauracionBbdd, BbddRegistrada...)
├── config/        SecurityConfig, DataInitializer
├── controller/    HomeController, BbddController (módulo 1), AnalisisController, LogsController,
│                  RegistroController, UsuarioController, UploadErrorHandler
├── form/          CreacionBbddForm, ServidorForm, AnalisisForm, RegistroForm, UsuarioForm
├── model/         Usuario, Rol, BbddPropietario
├── repository/    UsuarioRepository, BbddPropietarioRepository
├── security/      UsuarioDetailsService
└── service/       UsuarioService, PermisosBbdd
src/main/resources
├── application.properties
├── static/css/app.css
├── static/js/carga.js   reloj de la carga de datos (paso 6)
└── templates/           login, registro, dashboard, bbdd, analisis, logs, usuarios, usuario-form,
                         acceso-denegado, error, fragments/layout
```

## Tests

`mvn test` ejecuta los tests de la WebApp. No necesitan ni la API ni PostgreSQL: la API se sustituye por un
simulacro (`@MockitoBean ApiPythonClient`) y H2 va en memoria (`src/test/resources/application.properties`),
independiente del fichero `./data/sqlanalyzer`.

| Clase | Qué comprueba |
|-------|---------------|
| `BbddTests` | Pasos 1 a 8 del módulo 1: validación del DDL, prototipo, creación, inserción, ANALYZE, exportación, registro y descarga de dumps |
| `ServidorTests` | Paso 9: probar conexión, restaurar y recordar la contraseña solo en la sesión |
| `FilasPorDefectoTests` | Filas que se proponen por defecto en el paso 3 |
| `RolesTests` | Qué ve y qué puede hacer cada rol (paso 9, registro, dumps, progreso de la carga) |
| `SecurityTests` | Redirección a login, credenciales, permisos, CSRF, validación de formularios y subida de logs |
| `UsuarioTests` | Registro público, gestión de usuarios y propietarios de las BBDD al renombrar o eliminar |

Los tests de la API se lanzan aparte con `pytest` (ver [`api-python/README.md`](api-python/README.md)).
