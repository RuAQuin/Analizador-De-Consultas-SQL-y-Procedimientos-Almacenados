package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.Arbol;
import es.tfg.sqlanalyzer.api.ArbolOrdenado;
import es.tfg.sqlanalyzer.api.ClaveForanea;
import es.tfg.sqlanalyzer.api.ColumnaPrototipo;
import es.tfg.sqlanalyzer.api.CreacionBbdd;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.NodoArbol;
import es.tfg.sqlanalyzer.api.PrototipoDatos;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.TablaCreada;
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

import java.util.List;
import java.util.Map;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
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
}
