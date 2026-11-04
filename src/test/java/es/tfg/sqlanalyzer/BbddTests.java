package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.Arbol;
import es.tfg.sqlanalyzer.api.ClaveForanea;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.NodoArbol;
import es.tfg.sqlanalyzer.api.TablaIntermedia;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Paso 1 del módulo 1: el DDL escrito por el usuario se valida en la API Python (pglast). */
@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(roles = "ADMIN")
class BbddTests {

    private static final String DDL = "CREATE TABLE clientes (id integer PRIMARY KEY);";

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ApiPythonClient api;

    @Test
    // Si el DDL es correcto, se redirige a la pantalla mostrando el orden de Kahn y las FK (paso 2.1).
    void ddlValidoMuestraOrdenYClavesForaneas() throws Exception {
        var orden = List.of(new TablaOrdenada("clientes", 0), new TablaOrdenada("compras", 1));
        var fks = List.of(new ClaveForanea("compras", List.of("cliente_id"), "clientes", List.of("id")));
        when(api.validarDdl(DDL)).thenReturn(
                new ValidacionDdl(true, List.of("compras", "clientes"), List.of(), fks, orden, List.of(), DDL, List.of()));

        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", DDL))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("orden", orden))
           .andExpect(flash().attribute("clavesForaneas", fks));
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
                List.of(new TablaOrdenada("productos", 0)), List.of(), DDL, arboles));

        var flash = mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", DDL))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("arboles", arboles))
           .andReturn().getFlashMap();

        mvc.perform(get("/bbdd").flashAttrs(flash))
           .andExpect(content().string(containsString("Árboles de agrupación")))
           .andExpect(content().string(containsString("Árbol 2")))
           .andExpect(content().string(containsString("└─ compras")))
           .andExpect(content().string(containsString("   └─ lineas_compra")))
           .andExpect(content().string(containsString("por compra_id")));
    }

    @Test
    // Si la API ha roto un ciclo con una tabla intermedia, la pantalla lo indica y muestra el DDL final.
    void cicloResueltoMuestraTablaIntermediaYDdlFinal() throws Exception {
        var fkApartada = new ClaveForanea("departamentos", List.of("responsable_id"), "empleados", List.of("id"));
        var intermedias = List.of(new TablaIntermedia("departamentos_responsable", fkApartada));
        String ddlFinal = "CREATE TABLE departamentos_responsable (departamentos_id integer PRIMARY KEY);";
        when(api.validarDdl(DDL)).thenReturn(new ValidacionDdl(true, List.of("clientes"), List.of(), List.of(),
                List.of(new TablaOrdenada("clientes", 0)), intermedias, ddlFinal, List.of()));

        var flash = mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", DDL))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("tablasIntermedias", intermedias))
           .andExpect(flash().attribute("aviso", containsString("1 tabla(s) intermedia(s)")))
           .andReturn().getFlashMap();

        mvc.perform(get("/bbdd").flashAttrs(flash))
           .andExpect(content().string(containsString("Ciclos resueltos con tablas intermedias")))
           .andExpect(content().string(containsString("departamentos (responsable_id) → empleados (id)")))
           .andExpect(content().string(containsString("CREATE TABLE departamentos_responsable")));
    }

    @Test
    // Una FK a una tabla no definida (o un ciclo) vuelve al formulario como cualquier otro error del DDL.
    void fkATablaNoDefinidaVuelveAlFormulario() throws Exception {
        String ddl = "CREATE TABLE compras (cliente_id int REFERENCES clientes(id));";
        when(api.validarDdl(ddl)).thenReturn(new ValidacionDdl(false, List.of("compras"),
                List.of(new ErrorDdl("La FK de «compras» (cliente_id) referencia la tabla «clientes», que no está definida en el DDL", 1, 34)),
                List.of(), List.of(), List.of(), null, List.of()));

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
                List.of(new ErrorDdl("Error de sintaxis: syntax error at or near \"TABLA\"", 1, 8)), List.of(), List.of(), List.of(), null, List.of()));

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
}
