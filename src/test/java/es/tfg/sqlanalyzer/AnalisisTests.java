package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.api.AnalisisConsulta;
import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.BbddRegistrada;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.model.BbddPropietario;
import es.tfg.sqlanalyzer.repository.BbddPropietarioRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.OffsetDateTime;
import java.util.List;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Módulo 2, parte 1: el SQL y la BBDD objetivo, con la API simulada.
 * Registro: «mia» (de pepe), «ajena» (de otro), «borrada» (ya no existe) y la copia de «mia» en otro equipo.
 */
@SpringBootTest
@AutoConfigureMockMvc
class AnalisisTests {

    private static final OffsetDateTime REGISTRADA = OffsetDateTime.parse("2026-11-24T10:15:00Z");

    @Autowired
    MockMvc mvc;

    @Autowired
    BbddPropietarioRepository propietarios;

    @MockitoBean
    ApiPythonClient api;

    @BeforeEach
    void propietariosYRegistro() {
        propietarios.deleteAll();
        propietarios.save(new BbddPropietario("mia", "pepe"));
        propietarios.save(new BbddPropietario("ajena", "otro"));
        propietarios.save(new BbddPropietario("borrada", "pepe"));
        when(api.listarRegistro()).thenReturn(List.of(
                new BbddRegistrada("mia", 1, 3, "mia_20261124_101500.dump", 900, REGISTRADA, null, "192.168.1.57:5432"),
                new BbddRegistrada("mia", 1, 3, "mia_20261124_101500.dump", 900, REGISTRADA, true, ""),
                new BbddRegistrada("ajena", 1, 5, "ajena_20261124_101500.dump", 900, REGISTRADA, true, ""),
                new BbddRegistrada("borrada", 1, 7, "borrada_20261101_090000.dump", 900, REGISTRADA, false, "")));
    }

    private static AnalisisConsulta recibido(String tipo, String bbdd) {
        return new AnalisisConsulta(true, List.of(), tipo, bbdd, bbdd == null ? null : "17.6");
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // USUARIO: en el desplegable solo sus BBDD del servidor de la aplicación que siguen existiendo.
    void usuarioSoloVeSusBbddObjetivo() throws Exception {
        mvc.perform(get("/analisis"))
           .andExpect(status().isOk())
           .andExpect(model().attribute("bbdds", List.of("mia")))
           .andExpect(content().string(containsString("Ninguna (solo análisis estático)")));
    }

    @Test
    @WithMockUser(username = "ana", roles = "ANALYST")
    // ANALYST (y ADMIN): todas, pero tampoco las borradas ni las copias de otros equipos.
    void analistaVeTodasLasBbddObjetivo() throws Exception {
        mvc.perform(get("/analisis")).andExpect(model().attribute("bbdds", List.of("mia", "ajena")));
    }

    @Test
    @WithMockUser(username = "nuevo", roles = "USUARIO")
    // Sin BBDD objetivo: se explica dónde generarlas.
    void sinBbddObjetivoSeExplicaDondeGenerarlas() throws Exception {
        mvc.perform(get("/analisis"))
           .andExpect(model().attribute("bbdds", List.of()))
           .andExpect(content().string(containsString("No tienes BBDD objetivo")));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // La casilla «Permitir EXPLAIN ANALYZE» sustituye a las de Explain Plan y EXPLAIN ANALYZE; viene marcada.
    void formularioConLaCasillaDeExplainAnalyze() throws Exception {
        mvc.perform(get("/analisis"))
           .andExpect(content().string(containsString("Permitir EXPLAIN ANALYZE (ejecuta la consulta)")))
           .andExpect(content().string(not(containsString("Explain Plan</span>"))));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // Con su BBDD: se envía a la API y se muestra el resultado en la misma página.
    void analizaConSuBbdd() throws Exception {
        when(api.analizarConsulta("SELECT 1", "CONSULTA", "mia")).thenReturn(recibido("CONSULTA", "mia"));
        mvc.perform(post("/analisis").with(csrf())
                .param("sql", "SELECT 1").param("tipo", "CONSULTA").param("bbddDestino", "mia"))
           .andExpect(status().isOk())
           .andExpect(model().attributeExists("resultado"))
           .andExpect(content().string(containsString("SQL recibido (consulta) para «mia» (PostgreSQL 17.6).")));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // Sin BBDD («Ninguna»): se envía null y solo habrá análisis estático. El tipo llega a la API.
    void sinBbddSoloAnalisisEstatico() throws Exception {
        when(api.analizarConsulta("CALL p()", "PROCEDIMIENTO", null)).thenReturn(recibido("PROCEDIMIENTO", null));
        mvc.perform(post("/analisis").with(csrf())
                .param("sql", "CALL p()").param("tipo", "PROCEDIMIENTO").param("bbddDestino", ""))
           .andExpect(content().string(containsString(
                   "SQL recibido (procedimiento) sin BBDD objetivo: solo análisis estático.")));
        verify(api).analizarConsulta("CALL p()", "PROCEDIMIENTO", null);
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // Una BBDD que no está en su desplegable (ajena, borrada o inventada) se rechaza sin llamar a la API.
    void bbddQueNoEstaEnElDesplegableSeRechaza() throws Exception {
        for (String bbdd : List.of("ajena", "borrada", "sqlanalyzer_repositorio")) {
            mvc.perform(post("/analisis").with(csrf())
                    .param("sql", "SELECT 1").param("tipo", "CONSULTA").param("bbddDestino", bbdd))
               .andExpect(status().isOk())
               .andExpect(model().attributeHasFieldErrors("form", "bbddDestino"))
               .andExpect(content().string(containsString("Elige una de tus BBDD objetivo del módulo 1")));
        }
        verify(api, never()).analizarConsulta(anyString(), anyString(), any());
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // Si la API rechaza la BBDD (por ejemplo, se ha borrado justo antes), se muestra su motivo.
    void erroresDeLaApiSeMuestran() throws Exception {
        when(api.analizarConsulta("SELECT 1", "CONSULTA", "mia")).thenReturn(new AnalisisConsulta(false,
                List.of(new ErrorDdl("«mia» está en el registro, pero ya no existe en el servidor", null, null)),
                "CONSULTA", null, null));
        mvc.perform(post("/analisis").with(csrf())
                .param("sql", "SELECT 1").param("tipo", "CONSULTA").param("bbddDestino", "mia"))
           .andExpect(content().string(containsString("No se ha podido analizar")))
           .andExpect(content().string(containsString("ya no existe en el servidor")))
           .andExpect(content().string(not(containsString("SQL recibido"))));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // API parada al analizar: aviso, y el SQL escrito se conserva.
    void apiNoDisponibleAlAnalizar() throws Exception {
        when(api.analizarConsulta(anyString(), anyString(), any()))
                .thenThrow(new ApiNoDisponibleException("No se ha podido contactar con la API Python", null));
        mvc.perform(post("/analisis").with(csrf())
                .param("sql", "SELECT 42").param("tipo", "CONSULTA").param("bbddDestino", "mia"))
           .andExpect(status().isOk())
           .andExpect(model().attributeExists("error"))
           .andExpect(content().string(containsString("SELECT 42")));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // API parada al leer el registro: la pantalla se abre igual, con el aviso y sin BBDD en el desplegable.
    void registroNoDisponible() throws Exception {
        when(api.listarRegistro()).thenThrow(new ApiNoDisponibleException("API parada", null));
        mvc.perform(get("/analisis"))
           .andExpect(status().isOk())
           .andExpect(model().attribute("bbdds", List.of()))
           .andExpect(content().string(containsString("No se han podido leer las BBDD objetivo")));
    }
}
