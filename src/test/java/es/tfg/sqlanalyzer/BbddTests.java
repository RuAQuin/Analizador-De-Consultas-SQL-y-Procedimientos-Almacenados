package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.ErrorDdl;
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
    // Si pglast parsea el DDL, se redirige a la pantalla mostrando las tablas detectadas.
    void ddlValidoMuestraLasTablas() throws Exception {
        when(api.validarDdl(DDL)).thenReturn(new ValidacionDdl(true, List.of("clientes"), List.of()));

        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "tienda").param("definicionTablas", DDL))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("tablas", List.of("clientes")));
    }

    @Test
    // Si pglast no parsea el DDL, se vuelve al formulario con el texto escrito y el error con su posición.
    void ddlInvalidoVuelveAlFormularioConElError() throws Exception {
        String ddl = "CREATE TABLA clientes (id int);";
        when(api.validarDdl(ddl)).thenReturn(new ValidacionDdl(false, List.of(),
                List.of(new ErrorDdl("Error de sintaxis: syntax error at or near \"TABLA\"", 1, 8))));

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
