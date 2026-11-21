package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.api.AnalisisBbdd;
import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.BbddRegistrada;
import es.tfg.sqlanalyzer.api.Arbol;
import es.tfg.sqlanalyzer.api.ArbolOrdenado;
import es.tfg.sqlanalyzer.api.ClaveForanea;
import es.tfg.sqlanalyzer.api.ColumnaPrototipo;
import es.tfg.sqlanalyzer.api.CreacionBbdd;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.ExportacionBbdd;
import es.tfg.sqlanalyzer.api.InsercionDatos;
import es.tfg.sqlanalyzer.api.NodoArbol;
import es.tfg.sqlanalyzer.api.PrototipoDatos;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.TablaAnalizada;
import es.tfg.sqlanalyzer.api.TablaCreada;
import es.tfg.sqlanalyzer.api.TablaInsertada;
import es.tfg.sqlanalyzer.api.TablaPrototipo;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Módulo 1: validación del DDL (pasos 1 y 2), prototipo de datos (paso 3) y creación de la BBDD (pasos 4 y 5),
 * con la API Python simulada. */
@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(roles = "ADMIN")
class BbddTests {

    private static final String DDL = "CREATE TABLE clientes (id integer PRIMARY KEY);";

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ApiPythonClient api;

    // Valida el DDL (con la respuesta simulada de la API) y devuelve la sesión resultante.
    private MockHttpSession validarDdl() throws Exception {
        return (MockHttpSession) mvc.perform(post("/bbdd").with(csrf())
                        .param("nombreBbdd", "tienda").param("definicionTablas", DDL))
                .andExpect(redirectedUrl("/bbdd"))
                .andReturn().getRequest().getSession();
    }

    // --- Paso 3: prototipo de datos ---

    private static final List<TablaOrdenada> ORDEN = List.of(new TablaOrdenada("clientes", 0), new TablaOrdenada("compras", 1));

    private MockHttpSession validarDdlConDosTablas() throws Exception {
        var fk = new ClaveForanea("compras", List.of("cliente_id"), "clientes", List.of("id"));
        when(api.validarDdl(DDL)).thenReturn(new ValidacionDdl(true, List.of("clientes", "compras"), List.of(),
                List.of(fk), ORDEN, List.of(), List.of()));
        return validarDdl();
    }

    @Test
    // Tras validar el DDL aparece el formulario del prototipo con 10 filas por defecto en cada tabla.
    void trasValidarElDdlSePidenLasFilasDeCadaTabla() throws Exception {
        mvc.perform(get("/bbdd").session(validarDdlConDosTablas()))
           .andExpect(content().string(containsString("3. Prototipo de datos")))
           .andExpect(content().string(containsString("name=\"filas[clientes]\"")))
           .andExpect(content().string(containsString("name=\"filas[compras]\"")))
           .andExpect(content().string(containsString("value=\"10\"")));
    }

    @Test
    // Si el prototipo es correcto, se guarda en la sesión y se muestra la vista previa de cada tabla.
    void prototipoCorrectoMuestraLaVistaPrevia() throws Exception {
        var sesion = validarDdlConDosTablas();
        var prototipo = new PrototipoDatos(true, List.of(), List.of(
                new TablaPrototipo("clientes", 3, List.of(new ColumnaPrototipo("id", "serial", "auto"),
                        new ColumnaPrototipo("nombre", "varchar(100)", "tipo")),
                        List.of(List.of("(auto)", "AAA"), List.of("(auto)", "BBB"), List.of("(auto)", "CCC"))),
                new TablaPrototipo("compras", 6, List.of(new ColumnaPrototipo("cliente_id", "integer", "fk")),
                        List.of(List.of("1"), List.of("2")))));
        when(api.definirPrototipo(DDL, Map.of("clientes", 3, "compras", 6))).thenReturn(prototipo);

        mvc.perform(post("/bbdd/prototipo").with(csrf()).session(sesion)
                        .param("filas[clientes]", "3").param("filas[compras]", "6"))
           .andExpect(redirectedUrl("/bbdd#prototipo"))
           .andExpect(request().sessionAttribute("bbdd.prototipo", prototipo));

        mvc.perform(get("/bbdd").session(sesion))
           .andExpect(content().string(containsString("Vista previa")))
           .andExpect(content().string(containsString("3 filas · se muestran 3")))
           .andExpect(content().string(containsString("BBB")))
           .andExpect(content().string(containsString(">FK<")))
           .andExpect(content().string(containsString(">auto<")))
           .andExpect(content().string(containsString("value=\"6\"")));
    }

    @Test
    // Un aviso de coherencia vuelve a la pantalla con las filas escritas para corregirlas.
    void prototipoConAvisoVuelveConLasFilasEscritas() throws Exception {
        var sesion = validarDdlConDosTablas();
        when(api.definirPrototipo(DDL, Map.of("clientes", 0, "compras", 6))).thenReturn(new PrototipoDatos(false,
                List.of(new ErrorDdl("«compras» tiene 6 filas, pero su FK NOT NULL (cliente_id) apunta a «clientes», que tiene 0 filas", null, null)),
                List.of()));

        mvc.perform(post("/bbdd/prototipo").with(csrf()).session(sesion)
                        .param("filas[clientes]", "0").param("filas[compras]", "6"))
           .andExpect(status().isOk())
           .andExpect(view().name("bbdd"))
           .andExpect(content().string(containsString("Aviso de coherencia")))
           .andExpect(content().string(containsString("que tiene 0 filas")))
           .andExpect(content().string(containsString("value=\"0\"")))
           .andExpect(request().sessionAttribute("bbdd.prototipo", (Object) null));
    }

    @Test
    // Si una cantidad no es un número, se avisa sin llamar a la API.
    void filasQueNoSonNumerosNoLlamanALaApi() throws Exception {
        var sesion = validarDdlConDosTablas();
        mvc.perform(post("/bbdd/prototipo").with(csrf()).session(sesion)
                        .param("filas[clientes]", "muchas").param("filas[compras]", "6"))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("El número de filas de «clientes» debe ser un número entero")));
        verify(api, never()).definirPrototipo(anyString(), anyMap());
    }

    @Test
    // Sin un DDL validado no se puede definir el prototipo.
    void prototipoSinDdlValidado() throws Exception {
        mvc.perform(post("/bbdd/prototipo").with(csrf()).param("filas[clientes]", "3"))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", "Primero valida el DDL de las tablas."));
    }

    @Test
    // Validar otro DDL borra de la sesión el DDL anterior y su prototipo.
    void nuevoDdlLimpiaLaSesion() throws Exception {
        var sesion = validarDdlConDosTablas();
        String otro = "CREATE TABLA x (id int);";
        when(api.validarDdl(otro)).thenReturn(new ValidacionDdl(false, List.of(),
                List.of(new ErrorDdl("Error de sintaxis", 1, 8)), List.of(), List.of(), List.of(), List.of()));

        mvc.perform(post("/bbdd").with(csrf()).session(sesion).param("nombreBbdd", "tienda").param("definicionTablas", otro))
           .andExpect(status().isOk())
           .andExpect(request().sessionAttribute("bbdd.validacion", (Object) null))
           .andExpect(content().string(not(containsString("3. Prototipo de datos"))));
    }

    @Test
    // Si el DDL es correcto, se redirige a la pantalla mostrando el orden de Kahn y las FK (paso 2.1).
    void ddlValidoMuestraOrdenYClavesForaneas() throws Exception {
        var orden = List.of(new TablaOrdenada("clientes", 0), new TablaOrdenada("compras", 1));
        var fks = List.of(new ClaveForanea("compras", List.of("cliente_id"), "clientes", List.of("id")));
        var validacion = new ValidacionDdl(true, List.of("compras", "clientes"), List.of(), fks, orden, List.of(), List.of());
        when(api.validarDdl(DDL)).thenReturn(validacion);

        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", DDL))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(request().sessionAttribute("bbdd.validacion", validacion));
    }

    @Test
    // La pantalla muestra el orden de creación y las FK recibidas de la API.
    void pantallaMuestraOrdenYClavesForaneas() throws Exception {
        var orden = List.of(new TablaOrdenada("clientes", 0), new TablaOrdenada("compras", 1));
        var fks = List.of(new ClaveForanea("compras", List.of("cliente_id"), "clientes", List.of()));

        mvc.perform(get("/bbdd").flashAttr("orden", orden).flashAttr("clavesForaneas", fks))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("Orden de creación (Kahn)")))
           .andExpect(content().string(containsString("compras (cliente_id) → clientes (PK)")));
    }

    @Test
    // Paso 2.2: la pantalla dibuja los árboles de agrupación con la FK por la que cuelga cada tabla.
    void pantallaMuestraArbolesDeAgrupacion() throws Exception {
        var fkCompras = new ClaveForanea("compras", List.of("cliente_id"), "clientes", List.of("id"));
        var fkLineas = new ClaveForanea("lineas_compra", List.of("compra_id"), "compras", List.of("id"));
        var arboles = List.of(
                new Arbol("productos", List.of(new NodoArbol("productos", null, 0, null))),
                new Arbol("clientes", List.of(
                        new NodoArbol("clientes", null, 0, null),
                        new NodoArbol("compras", "clientes", 1, fkCompras),
                        new NodoArbol("lineas_compra", "compras", 2, fkLineas))));
        when(api.validarDdl(DDL)).thenReturn(new ValidacionDdl(true, List.of(), List.of(), List.of(fkCompras, fkLineas),
                List.of(new TablaOrdenada("productos", 0)), arboles, List.of()));

        mvc.perform(get("/bbdd").session(validarDdl()))
           .andExpect(content().string(containsString("Árboles de agrupación")))
           .andExpect(content().string(containsString("Árbol 2")))
           .andExpect(content().string(containsString("└─ compras")))
           .andExpect(content().string(containsString("   └─ lineas_compra")))
           .andExpect(content().string(containsString("por compra_id")));
    }

    @Test
    // Paso 2.3: la pantalla muestra el orden de carga de los árboles y por qué FK depende cada uno.
    void pantallaMuestraOrdenDeCargaDeLosArboles() throws Exception {
        var fkProducto = new ClaveForanea("lineas_compra", List.of("producto_id"), "productos", List.of("id"));
        var ordenCarga = List.of(
                new ArbolOrdenado("productos", 0, List.of(), List.of()),
                new ArbolOrdenado("clientes", 1, List.of("productos"), List.of(fkProducto)));
        when(api.validarDdl(DDL)).thenReturn(new ValidacionDdl(true, List.of(), List.of(), List.of(fkProducto),
                List.of(new TablaOrdenada("productos", 0)), List.of(), ordenCarga));

        mvc.perform(get("/bbdd").session(validarDdl()))
           .andExpect(content().string(containsString("Orden de carga de los árboles (Kahn)")))
           .andExpect(content().string(containsString("lineas_compra (producto_id) → productos (id)")));
    }

    @Test
    // Los ciclos no se resuelven: llegan como error y se vuelve al formulario con el DDL escrito.
    void cicloVuelveAlFormularioConElError() throws Exception {
        String ddl = "CREATE TABLE a (id int PRIMARY KEY, b_id int REFERENCES b);\nCREATE TABLE b (id int PRIMARY KEY, a_id int REFERENCES a);";
        when(api.validarDdl(ddl)).thenReturn(new ValidacionDdl(false, List.of("a", "b"),
                List.of(new ErrorDdl("Hay un ciclo de FK entre las tablas «a», «b»: ninguna puede crearse antes que las demás", 1, 1)),
                List.of(), List.of(), List.of(), List.of()));

        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", ddl))
           .andExpect(status().isOk())
           .andExpect(view().name("bbdd"))
           .andExpect(model().attributeHasFieldErrorCode("form", "definicionTablas", "ddl.invalido"))
           .andExpect(content().string(containsString("Línea 1, columna 1: Hay un ciclo de FK entre las tablas «a», «b»")))
           .andExpect(content().string(containsString("REFERENCES b")));
    }

    @Test
    // Una FK a una tabla no definida (o un ciclo) vuelve al formulario como cualquier otro error del DDL.
    void fkATablaNoDefinidaVuelveAlFormulario() throws Exception {
        String ddl = "CREATE TABLE compras (cliente_id int REFERENCES clientes(id));";
        when(api.validarDdl(ddl)).thenReturn(new ValidacionDdl(false, List.of("compras"),
                List.of(new ErrorDdl("La FK de «compras» (cliente_id) referencia la tabla «clientes», que no está definida en el DDL", 1, 34)),
                List.of(), List.of(), List.of(), List.of()));

        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", ddl))
           .andExpect(status().isOk())
           .andExpect(view().name("bbdd"))
           .andExpect(content().string(containsString("Línea 1, columna 34: La FK de «compras»")));
    }

    @Test
    // Si pglast no parsea el DDL, se vuelve al formulario con el texto escrito y el error con su posición.
    void ddlInvalidoVuelveAlFormularioConElError() throws Exception {
        String ddl = "CREATE TABLA clientes (id int);";
        when(api.validarDdl(ddl)).thenReturn(new ValidacionDdl(false, List.of(),
                List.of(new ErrorDdl("Error de sintaxis: syntax error at or near \"TABLA\"", 1, 8)), List.of(), List.of(), List.of(), List.of()));

        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", ddl))
           .andExpect(status().isOk())
           .andExpect(view().name("bbdd"))
           .andExpect(model().attributeHasFieldErrorCode("form", "definicionTablas", "ddl.invalido"))
           .andExpect(content().string(containsString("Línea 1, columna 8: Error de sintaxis")))
           .andExpect(content().string(containsString("CREATE TABLA clientes")));
    }

    @Test
    // Si la API no responde, se avisa al usuario sin perder lo que había escrito.
    void apiNoDisponible() throws Exception {
        when(api.validarDdl(anyString())).thenThrow(new ApiNoDisponibleException("No se ha podido contactar con la API Python", null));

        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", DDL))
           .andExpect(status().isOk())
           .andExpect(model().attribute("error", containsString("API Python")));
    }

    @Test
    // Si el formulario no es válido, no se llama a la API.
    void formularioInvalidoNoLlamaALaApi() throws Exception {
        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", " "))
           .andExpect(status().isOk())
           .andExpect(model().attributeHasFieldErrors("form", "definicionTablas"));
        verify(api, never()).validarDdl(anyString());
    }

    // --- Pasos 4 y 5: revisión, confirmación y CREATE DATABASE / CREATE TABLE ---

    private static final Map<String, Integer> FILAS = Map.of("clientes", 3, "compras", 6);

    // Valida el DDL y genera un prototipo correcto: devuelve la sesión lista para confirmar.
    private MockHttpSession conPrototipo() throws Exception {
        var sesion = validarDdlConDosTablas();
        when(api.definirPrototipo(DDL, FILAS)).thenReturn(new PrototipoDatos(true, List.of(), List.of(
                new TablaPrototipo("clientes", 3, List.of(new ColumnaPrototipo("id", "integer", "tipo")), List.of()),
                new TablaPrototipo("compras", 6, List.of(new ColumnaPrototipo("cliente_id", "integer", "fk")), List.of()))));
        mvc.perform(post("/bbdd/prototipo").with(csrf()).session(sesion)
                        .param("filas[clientes]", "3").param("filas[compras]", "6"))
           .andExpect(redirectedUrl("/bbdd#prototipo"));
        return sesion;
    }

    private static CreacionBbdd creada() {
        return new CreacionBbdd(true, List.of(), "tienda", List.of(), List.of(
                new TablaCreada("clientes", "CREATE TABLE clientes (id integer PRIMARY KEY)"),
                new TablaCreada("compras", "CREATE TABLE compras (cliente_id integer REFERENCES clientes (id))")));
    }

    @Test
    // Con el prototipo correcto aparece el resumen y el botón para confirmar.
    void conPrototipoSeMuestraElResumenYElBoton() throws Exception {
        mvc.perform(get("/bbdd").session(conPrototipo()))
           .andExpect(content().string(containsString("4. Revisión y confirmación")))
           .andExpect(content().string(containsString("Confirmar y crear la BBDD")))
           .andExpect(content().string(containsString("clientes → compras")))
           .andExpect(content().string(containsString(">9<")));
    }

    @Test
    // Sin prototipo no aparece el botón.
    void sinPrototipoNoHayBoton() throws Exception {
        mvc.perform(get("/bbdd").session(validarDdlConDosTablas()))
           .andExpect(content().string(not(containsString("Confirmar y crear la BBDD"))));
    }

    @Test
    // Al confirmar se crea la BBDD: se guarda en la sesión, se muestran las tablas creadas y se bloquean las filas.
    void confirmarCreaLaBbdd() throws Exception {
        var sesion = conPrototipo();
        var creacion = creada();
        when(api.crearBbdd("tienda", DDL, FILAS)).thenReturn(creacion);

        mvc.perform(post("/bbdd/crear").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd#creacion"))
           .andExpect(flash().attribute("aviso", containsString("«tienda» con 2 tablas")))
           .andExpect(request().sessionAttribute("bbdd.creacion", creacion));

        mvc.perform(get("/bbdd").session(sesion))
           .andExpect(content().string(containsString("CREATE TABLE compras (cliente_id integer REFERENCES clientes (id))")))
           .andExpect(content().string(not(containsString("Confirmar y crear la BBDD"))))
           .andExpect(content().string(containsString("disabled")));
    }

    @Test
    // Si la API no crea la BBDD (por ejemplo, porque ya existe), se avisa y se puede volver a intentar.
    void bbddQueYaExisteMuestraElAviso() throws Exception {
        var sesion = conPrototipo();
        when(api.crearBbdd("tienda", DDL, FILAS)).thenReturn(new CreacionBbdd(false,
                List.of(new ErrorDdl("Ya existe una base de datos «tienda» en el servidor: elige otro nombre", null, null)),
                null, List.of(), List.of()));

        mvc.perform(post("/bbdd/crear").with(csrf()).session(sesion))
           .andExpect(status().isOk())
           .andExpect(view().name("bbdd"))
           .andExpect(content().string(containsString("No se ha creado la base de datos")))
           .andExpect(content().string(containsString("Ya existe una base de datos «tienda»")))
           .andExpect(content().string(containsString("Confirmar y crear la BBDD")))
           .andExpect(request().sessionAttribute("bbdd.creacion", (Object) null));
    }

    @Test
    // Si la API no responde al confirmar, se avisa sin perder el prototipo.
    void apiNoDisponibleAlConfirmar() throws Exception {
        var sesion = conPrototipo();
        when(api.crearBbdd(anyString(), anyString(), anyMap()))
                .thenThrow(new ApiNoDisponibleException("No se ha podido contactar con la API Python", null));

        mvc.perform(post("/bbdd/crear").with(csrf()).session(sesion))
           .andExpect(status().isOk())
           .andExpect(model().attribute("error", containsString("API Python")))
           .andExpect(content().string(containsString("Vista previa")));
    }

    @Test
    // Sin prototipo no se puede confirmar.
    void confirmarSinPrototipo() throws Exception {
        mvc.perform(post("/bbdd/crear").with(csrf()).session(validarDdlConDosTablas()))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", "Primero genera la vista previa del prototipo de datos."));
        verify(api, never()).crearBbdd(anyString(), anyString(), anyMap());
    }

    @Test
    // Una vez creada, no se puede crear otra vez ni cambiar el prototipo.
    void bbddCreadaNoSeVuelveACrear() throws Exception {
        var sesion = conPrototipo();
        when(api.crearBbdd("tienda", DDL, FILAS)).thenReturn(creada());
        mvc.perform(post("/bbdd/crear").with(csrf()).session(sesion)).andExpect(redirectedUrl("/bbdd#creacion"));

        mvc.perform(post("/bbdd/crear").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", containsString("ya está creada")));
        mvc.perform(post("/bbdd/prototipo").with(csrf()).session(sesion)
                        .param("filas[clientes]", "1").param("filas[compras]", "1"))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", containsString("ya está creada")));
        verify(api, times(1)).crearBbdd(anyString(), anyString(), anyMap());
    }

    // --- Paso 6: inserción de datos ---

    // Valida el DDL, genera el prototipo y crea la BBDD: devuelve la sesión lista para insertar.
    private MockHttpSession conBbddCreada() throws Exception {
        var sesion = conPrototipo();
        when(api.crearBbdd("tienda", DDL, FILAS)).thenReturn(creada());
        mvc.perform(post("/bbdd/crear").with(csrf()).session(sesion)).andExpect(redirectedUrl("/bbdd#creacion"));
        return sesion;
    }

    private static InsercionDatos insertada() {
        return new InsercionDatos(true, List.of(), "tienda",
                List.of(new TablaInsertada("clientes", 3), new TablaInsertada("compras", 6)), 0.12);
    }

    @Test
    // Con la BBDD creada aparece el botón para insertar las filas del prototipo.
    void conLaBbddCreadaSeMuestraElBotonDeInsertar() throws Exception {
        mvc.perform(get("/bbdd").session(conBbddCreada()))
           .andExpect(content().string(containsString("6. Inserción de datos")))
           .andExpect(content().string(containsString("Insertar 9 filas")));
    }

    @Test
    // Sin BBDD creada no aparece el botón.
    void sinBbddNoHayBotonDeInsertar() throws Exception {
        mvc.perform(get("/bbdd").session(conPrototipo()))
           .andExpect(content().string(not(containsString("6. Inserción de datos"))));
    }

    @Test
    // Al insertar se guarda en la sesión y se muestran las filas de cada tabla.
    void insertarMuestraLasFilasDeCadaTabla() throws Exception {
        var sesion = conBbddCreada();
        var insercion = insertada();
        when(api.insertarDatos("tienda", DDL, FILAS)).thenReturn(insercion);

        mvc.perform(post("/bbdd/insertar").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd#insercion"))
           .andExpect(flash().attribute("aviso", containsString("Se han insertado 9 filas en «tienda»")))
           .andExpect(request().sessionAttribute("bbdd.insercion", insercion));

        mvc.perform(get("/bbdd").session(sesion))
           .andExpect(content().string(containsString("filas insertadas en")))
           .andExpect(content().string(containsString("(0.12 s)")))
           .andExpect(content().string(not(containsString("Insertar 9 filas"))));
    }

    @Test
    // Si una fila falla, se avisa y se puede reintentar.
    void filaQueFallaMuestraElAviso() throws Exception {
        var sesion = conBbddCreada();
        when(api.insertarDatos("tienda", DDL, FILAS)).thenReturn(new InsercionDatos(false,
                List.of(new ErrorDdl("PostgreSQL no ha podido insertar la fila 2 de «compras»: new row violates check constraint", null, null)),
                null, List.of(), 0));

        mvc.perform(post("/bbdd/insertar").with(csrf()).session(sesion))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("No se han insertado los datos")))
           .andExpect(content().string(containsString("la fila 2 de «compras»")))
           .andExpect(content().string(containsString("Insertar 9 filas")))
           .andExpect(request().sessionAttribute("bbdd.insercion", (Object) null));
    }

    @Test
    // Sin BBDD creada no se puede insertar.
    void insertarSinBbdd() throws Exception {
        mvc.perform(post("/bbdd/insertar").with(csrf()).session(conPrototipo()))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", "Primero crea la base de datos."));
        verify(api, never()).insertarDatos(anyString(), anyString(), anyMap());
    }

    @Test
    // Los datos solo se insertan una vez.
    void noSeInsertaDosVeces() throws Exception {
        var sesion = conBbddCreada();
        when(api.insertarDatos("tienda", DDL, FILAS)).thenReturn(insertada());
        mvc.perform(post("/bbdd/insertar").with(csrf()).session(sesion)).andExpect(redirectedUrl("/bbdd#insercion"));

        mvc.perform(post("/bbdd/insertar").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", containsString("ya están insertados")));
        verify(api, times(1)).insertarDatos(anyString(), anyString(), anyMap());
    }

    // --- Paso 7: ANALYZE ---

    // Valida el DDL, genera el prototipo, crea la BBDD e inserta los datos: devuelve la sesión lista para el ANALYZE.
    private MockHttpSession conDatosInsertados() throws Exception {
        var sesion = conBbddCreada();
        when(api.insertarDatos("tienda", DDL, FILAS)).thenReturn(insertada());
        mvc.perform(post("/bbdd/insertar").with(csrf()).session(sesion)).andExpect(redirectedUrl("/bbdd#insercion"));
        return sesion;
    }

    private static AnalisisBbdd analizada() {
        return new AnalisisBbdd(true, List.of(), "tienda",
                List.of(new TablaAnalizada("clientes", 3, -1, 3, 1, 1),
                        new TablaAnalizada("compras", 6, -1, 6, 1, 2)), 0.05);
    }

    @Test
    // Con los datos insertados aparece el botón del ANALYZE.
    void conLosDatosInsertadosSeMuestraElBotonDeAnalyze() throws Exception {
        mvc.perform(get("/bbdd").session(conDatosInsertados()))
           .andExpect(content().string(containsString("7. ANALYZE para cerrar la carga")))
           .andExpect(content().string(containsString("Ejecutar ANALYZE")));
    }

    @Test
    // Sin datos insertados no aparece la sección.
    void sinDatosNoHayAnalyze() throws Exception {
        mvc.perform(get("/bbdd").session(conBbddCreada()))
           .andExpect(content().string(not(containsString("7. ANALYZE"))));
    }

    @Test
    // Al analizar se guarda en la sesión y se muestran las estadísticas de cada tabla.
    void analyzeMuestraLasEstadisticasDeCadaTabla() throws Exception {
        var sesion = conDatosInsertados();
        var analisis = analizada();
        when(api.analizarBbdd("tienda", DDL, FILAS)).thenReturn(analisis);

        mvc.perform(post("/bbdd/analizar").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd#analisis"))
           .andExpect(flash().attribute("aviso", containsString("Se han analizado las 2 tablas de «tienda»")))
           .andExpect(request().sessionAttribute("bbdd.analisis", analisis));

        mvc.perform(get("/bbdd").session(sesion))
           .andExpect(content().string(containsString("tablas analizadas en")))
           .andExpect(content().string(containsString("sin analizar")))
           .andExpect(content().string(containsString("exacto")))
           .andExpect(content().string(not(containsString("Ejecutar ANALYZE"))));
    }

    @Test
    // Si el ANALYZE falla, se avisa y se puede reintentar.
    void analyzeQueFallaMuestraElAviso() throws Exception {
        var sesion = conDatosInsertados();
        when(api.analizarBbdd("tienda", DDL, FILAS)).thenReturn(new AnalisisBbdd(false,
                List.of(new ErrorDdl("La tabla «clientes» de «tienda» está vacía: inserta antes los datos (paso 6)", null, null)),
                null, List.of(), 0));

        mvc.perform(post("/bbdd/analizar").with(csrf()).session(sesion))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("No se han analizado las tablas")))
           .andExpect(content().string(containsString("está vacía")))
           .andExpect(content().string(containsString("Ejecutar ANALYZE")))
           .andExpect(request().sessionAttribute("bbdd.analisis", (Object) null));
    }

    @Test
    // Sin datos insertados no se puede analizar.
    void analyzeSinDatos() throws Exception {
        mvc.perform(post("/bbdd/analizar").with(csrf()).session(conBbddCreada()))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", "Primero inserta los datos."));
        verify(api, never()).analizarBbdd(anyString(), anyString(), anyMap());
    }

    @Test
    // El ANALYZE se hace una vez por carga.
    void noSeAnalizaDosVeces() throws Exception {
        var sesion = conDatosInsertados();
        when(api.analizarBbdd("tienda", DDL, FILAS)).thenReturn(analizada());
        mvc.perform(post("/bbdd/analizar").with(csrf()).session(sesion)).andExpect(redirectedUrl("/bbdd#analisis"));

        mvc.perform(post("/bbdd/analizar").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", containsString("ya están analizadas")));
        verify(api, times(1)).analizarBbdd(anyString(), anyString(), anyMap());
    }

    // --- Paso 8: pg_dump y registro ---

    private static final String DUMP = "tienda_20261118_101500.dump";
    private static final OffsetDateTime REGISTRADA = OffsetDateTime.parse("2026-11-18T10:15:00Z");

    // Valida, genera el prototipo, crea, inserta y analiza: devuelve la sesión lista para exportar.
    private MockHttpSession conAnalyze() throws Exception {
        var sesion = conDatosInsertados();
        when(api.analizarBbdd("tienda", DDL, FILAS)).thenReturn(analizada());
        mvc.perform(post("/bbdd/analizar").with(csrf()).session(sesion)).andExpect(redirectedUrl("/bbdd#analisis"));
        return sesion;
    }

    private static ExportacionBbdd exportada() {
        return new ExportacionBbdd(true, List.of(), "tienda", DUMP, 12_700, REGISTRADA, 0.3);
    }

    @Test
    // Con el ANALYZE hecho aparece el botón de exportar.
    void conAnalyzeSeMuestraElBotonDeExportar() throws Exception {
        mvc.perform(get("/bbdd").session(conAnalyze()))
           .andExpect(content().string(containsString("8. pg_dump y registro")))
           .andExpect(content().string(containsString("Exportar con pg_dump y registrar")));
    }

    @Test
    // Sin ANALYZE no aparece la sección.
    void sinAnalyzeNoHayExportacion() throws Exception {
        mvc.perform(get("/bbdd").session(conDatosInsertados()))
           .andExpect(content().string(not(containsString("8. pg_dump y registro"))));
    }

    @Test
    // Al exportar se muestra el enlace al script y la lista de BBDD registradas.
    void exportarMuestraElDumpYElRegistro() throws Exception {
        var sesion = conAnalyze();
        var exportacion = exportada();
        when(api.exportarBbdd("tienda", DDL, FILAS)).thenReturn(exportacion);
        when(api.listarRegistro()).thenReturn(List.of(
                new BbddRegistrada("tienda", 2, 9, DUMP, 12_700, REGISTRADA, true),
                new BbddRegistrada("antigua", 1, 5, "antigua_20261101_090000.sql", 900, REGISTRADA.minusDays(17), false)));

        mvc.perform(post("/bbdd/exportar").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd#exportacion"))
           .andExpect(flash().attribute("aviso", containsString("Se ha exportado «tienda» en " + DUMP + " (12.4 KB)")))
           .andExpect(request().sessionAttribute("bbdd.exportacion", exportacion));

        mvc.perform(get("/bbdd").session(sesion))
           .andExpect(content().string(containsString("href=\"/bbdd/dumps/" + DUMP + "\"")))
           .andExpect(content().string(containsString("/datos/dumps/" + DUMP)))
           .andExpect(content().string(containsString("BBDD objetivo registradas")))
           .andExpect(content().string(containsString("antigua_20261101_090000.sql")))
           .andExpect(content().string(containsString("900 B")))
           .andExpect(content().string(containsString("Borrada")))
           .andExpect(content().string(not(containsString("Exportar con pg_dump y registrar"))));
    }

    @Test
    // Si falla, se avisa y se puede reintentar.
    void exportacionQueFallaMuestraElAviso() throws Exception {
        var sesion = conAnalyze();
        when(api.exportarBbdd("tienda", DDL, FILAS)).thenReturn(new ExportacionBbdd(false,
                List.of(new ErrorDdl("pg_dump no ha podido exportar «tienda»: connection refused", null, null)),
                null, null, 0, null, 0));

        mvc.perform(post("/bbdd/exportar").with(csrf()).session(sesion))
           .andExpect(status().isOk())
           .andExpect(content().string(containsString("No se ha exportado la base de datos")))
           .andExpect(content().string(containsString("connection refused")))
           .andExpect(content().string(containsString("Exportar con pg_dump y registrar")))
           .andExpect(request().sessionAttribute("bbdd.exportacion", (Object) null));
    }

    @Test
    // Sin ANALYZE no se puede exportar.
    void exportarSinAnalyze() throws Exception {
        mvc.perform(post("/bbdd/exportar").with(csrf()).session(conDatosInsertados()))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", "Primero ejecuta el ANALYZE."));
        verify(api, never()).exportarBbdd(anyString(), anyString(), anyMap());
    }

    @Test
    // Se exporta una vez por carga.
    void noSeExportaDosVeces() throws Exception {
        var sesion = conAnalyze();
        when(api.exportarBbdd("tienda", DDL, FILAS)).thenReturn(exportada());
        mvc.perform(post("/bbdd/exportar").with(csrf()).session(sesion)).andExpect(redirectedUrl("/bbdd#exportacion"));

        mvc.perform(post("/bbdd/exportar").with(csrf()).session(sesion))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", containsString("ya está exportada y registrada")));
        verify(api, times(1)).exportarBbdd(anyString(), anyString(), anyMap());
    }

    @Test
    // La descarga copia el dump que envía la API, como fichero adjunto.
    void descargaElDump() throws Exception {
        doAnswer(i -> {
            i.getArgument(1, OutputStream.class).write("-- PostgreSQL database dump\n".getBytes(StandardCharsets.UTF_8));
            return true;
        }).when(api).descargarDump(eq(DUMP), any());

        mvc.perform(get("/bbdd/dumps/" + DUMP))
           .andExpect(status().isOk())
           .andExpect(header().string("Content-Disposition", "attachment; filename=\"" + DUMP + "\""))
           .andExpect(content().contentTypeCompatibleWith("application/octet-stream"))
           .andExpect(content().string("-- PostgreSQL database dump\n"));
    }

    @Test
    // Solo se piden a la API nombres de dump; el resto es 404.
    void descargaRechazaNombresQueNoSonDumps() throws Exception {
        mvc.perform(get("/bbdd/dumps/secreto.txt")).andExpect(status().isNotFound());
        when(api.descargarDump(eq(DUMP), any())).thenReturn(false);
        mvc.perform(get("/bbdd/dumps/" + DUMP)).andExpect(status().isNotFound());
        verify(api, times(1)).descargarDump(anyString(), any());
    }

    @Autowired
    private com.fasterxml.jackson.databind.ObjectMapper json;

    @Test
    // Las respuestas reales de la API (fechas ISO con microsegundos, snake_case) se leen bien.
    void leeLasRespuestasDeLaApi() throws Exception {
        var exportacion = json.readValue("""
                {"valido": true, "errores": [], "bbdd": "dump_e2e", "fichero": "dump_e2e_20261118_120752.sql",
                 "bytes": 379899, "registrada": "2026-11-18T12:07:52.595620Z", "segundos": 0.14}""", ExportacionBbdd.class);
        org.assertj.core.api.Assertions.assertThat(exportacion.registrada().toInstant().toString())
                .isEqualTo("2026-11-18T12:07:52.595620Z");
        org.assertj.core.api.Assertions.assertThat(exportacion.tamano()).isEqualTo("371.0 KB");

        var registrada = json.readValue("""
                {"nombre": "dump_e2e", "tablas": 2, "total_filas": 21000, "fichero": "dump_e2e_20261118_120752.sql",
                 "bytes": 379899, "registrada": "2026-11-18T12:07:52.595620Z", "existe": true}""", BbddRegistrada.class);
        org.assertj.core.api.Assertions.assertThat(registrada.totalFilas()).isEqualTo(21000);
        org.assertj.core.api.Assertions.assertThat(registrada.existe()).isTrue();
    }
}
