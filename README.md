# SQL Analyzer · WebApp

Interfaz web (Spring Boot 3.5 + Spring Security 6 + Thymeleaf, Java 21).
La WebApp nunca se conecta a las BBDD: todo pasa por la API Python (`app.api.url`,
variable `API_URL`, por defecto http://localhost:8000). Ver `api-python/README.md`.

## Arrancar

```bash
mvn spring-boot:run
# o
mvn package && java -jar target/sqlanalyzer-webapp-0.1.0.jar
```

Abrir http://localhost:8080

## Usuarios

Las cuentas se persisten en una BBDD propia H2 (fichero `./data/sqlanalyzer`,
tabla `usuarios`), gestionada con Spring Data JPA. Al arrancar por primera vez
(tabla vacía) se siembran dos cuentas iniciales:

| Usuario    | Contraseña    | Rol     | Acceso                                  |
|------------|---------------|---------|-----------------------------------------|
| `admin`    | `admin123`    | ADMIN   | Todo, incluida la gestión de usuarios   |
| `analista` | `analista123` | ANALYST | Análisis de consultas y logs (no BBDD)  |

Se cambian con las variables de entorno `APP_ADMIN_USER`, `APP_ADMIN_PASSWORD`,
`APP_ANALYST_USER` y `APP_ANALYST_PASSWORD` (solo tienen efecto la primera vez
que arranca la aplicación con la tabla vacía).

A partir de ahí, las cuentas se gestionan desde la propia aplicación:

- **Registro público** (`/registro`): cualquiera puede crear una cuenta con rol
  ANALYST. Enlazado desde la pantalla de login.
- **Login** (`/login`): formulario propio ya existente, ahora autenticando
  contra la BBDD de usuarios en lugar de credenciales en memoria.
- **CRUD de usuarios** (`/usuarios`, solo ADMIN): listar, crear, editar
  (usuario, contraseña opcional, rol, habilitado/deshabilitado) y eliminar
  cuentas. No se puede eliminar la propia cuenta ni dejar la aplicación sin
  ningún administrador.

## Seguridad aplicada

- Login por formulario propio (`/login`), logout por POST que invalida la sesión.
- Registro público (`/registro`) y gestión de usuarios (`/usuarios`, solo ADMIN).
- Contraseñas con BCrypt, nunca en claro ni en los formularios de edición.
- Autorización por rol: `/usuarios/**` solo ADMIN; `/bbdd/**`, `/analisis/**` y `/logs/**` ADMIN o ANALYST.
- CSRF activo en todos los formularios (incluida la subida de ficheros).
- Cabeceras: Content-Security-Policy sin scripts ni estilos inline, `frame-ancestors 'none'`, Referrer-Policy.
- Cookie de sesión `HttpOnly` y `SameSite=Strict`, caducidad 30 min, protección contra fijación de sesión.
- Página propia de acceso denegado (403) y de error.

## Estructura

```
src/main/java/es/tfg/sqlanalyzer
├── SqlAnalyzerApplication.java
├── config/        SecurityConfig, DataInitializer
├── controller/    HomeController, BbddController, AnalisisController, LogsController,
│                  RegistroController, UsuarioController, UploadErrorHandler
├── form/          CreacionBbddForm, AnalisisForm, RegistroForm, UsuarioForm
├── model/         Usuario, Rol
├── repository/    UsuarioRepository
├── security/      UsuarioDetailsService
└── service/       UsuarioService
src/main/resources
├── application.properties
├── static/css/app.css
└── templates/    login, registro, dashboard, bbdd, analisis, logs, usuarios, usuario-form,
                  acceso-denegado, error, fragments/layout
```

Los puntos de integración con la API Python están marcados con `TODO` en cada controlador.

## Tests

`mvn test` ejecuta:
- `SecurityTests`: redirección a login, credenciales, permisos por rol,
  rechazo de POST sin CSRF, validación de formularios y subida de logs.
- `UsuarioTests`: registro público (alta y validaciones), restricción de
  `/usuarios` a ADMIN y CRUD de usuarios.

Los tests usan una BBDD H2 en memoria propia (`src/test/resources/application.properties`),
independiente del fichero `./data/sqlanalyzer` usado en ejecución normal.
