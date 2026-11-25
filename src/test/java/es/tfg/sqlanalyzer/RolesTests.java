package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.api.AnalisisBbdd;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.InsercionDatos;
import es.tfg.sqlanalyzer.api.TablaAnalizada;
import es.tfg.sqlanalyzer.api.TablaInsertada;
import es.tfg.sqlanalyzer.api.BbddRegistrada;
import es.tfg.sqlanalyzer.api.ColumnaPrototipo;
import es.tfg.sqlanalyzer.api.CreacionBbdd;
import es.tfg.sqlanalyzer.api.ExportacionBbdd;
import es.tfg.sqlanalyzer.api.PrototipoDatos;
import es.tfg.sqlanalyzer.api.TablaCreada;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.TablaPrototipo;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import es.tfg.sqlanalyzer.form.CreacionBbddForm;
import es.tfg.sqlanalyzer.model.BbddPropietario;
import es.tfg.sqlanalyzer.repository.BbddPropietarioRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Permisos de los tres roles, con la API simulada:
 *  - ADMIN: todos los permisos. ANALYST: todas las BBDD y logs, sin paso 9. USUARIO: solo sus BBDD y logs, sin paso 9.
 */
@SpringBootTest
@AutoConfigureMockMvc
class RolesTests {

    private static final String DDL = "CREATE TABLE clientes (id integer PRIMARY KEY);";
    private static final OffsetDateTime REGISTRADA = OffsetDateTime.parse("2026-11-24T10:15:00Z");
    // «mia» es de pepe; «ajena», de otro usuario.
    private static final String DUMP_MIA = "mia_20261124_101500.dump";
    private static final String DUMP_AJENA = "ajena_20261124_101500.dump";

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
        when(api.listarRegistro()).thenReturn(List.of(
                new BbddRegistrada("mia", 1, 3, DUMP_MIA, 900, REGISTRADA, true, ""),
                new BbddRegistrada("ajena", 1, 5, DUMP_AJENA, 900, REGISTRADA, true, ""),
                new BbddRegistrada("antigua", 1, 7, "antigua_20261101_090000.sql", 900, REGISTRADA, false, "")));
        when(api.descargarDump(anyString(), any())).thenReturn(true);
    }

    // Sesión con el DDL validado y el prototipo de la BBDD «nombre» (pasos 1 a 3), lista para crearla.
    private static MockHttpSession conPrototipo(String nombre) {
        var sesion = new MockHttpSession();
        var form = new CreacionBbddForm();
        form.setNombreBbdd(nombre);
        form.setDefinicionTablas(DDL);
        sesion.setAttribute("bbdd.form", form);
        sesion.setAttribute("bbdd.validacion", new ValidacionDdl(true, List.of("clientes"), List.of(), List.of(),
                List.of(new TablaOrdenada("clientes", 0)), List.of(), List.of()));
        sesion.setAttribute("bbdd.filas", new LinkedHashMap<>(Map.of("clientes", "3")));
        sesion.setAttribute("bbdd.prototipo", new PrototipoDatos(true, List.of(), List.of(
                new TablaPrototipo("clientes", 3, List.of(new ColumnaPrototipo("id", "integer", "tipo")), List.of()))));
        return sesion;
    }

    private static CreacionBbdd creada(String nombre) {
        return new CreacionBbdd(true, List.of(), nombre, List.of(),
                List.of(new TablaCreada("clientes", "CREATE TABLE clientes (id integer PRIMARY KEY)")));
    }

    // Sesión con la BBDD «mia» ya exportada (pasos 1 a 8): así se muestran el registro y el paso 9.
    private static MockHttpSession exportada() {
        var sesion = conPrototipo("mia");
        sesion.setAttribute("bbdd.creacion", creada("mia"));
        sesion.setAttribute("bbdd.insercion", new InsercionDatos(true, List.of(), "mia",
                List.of(new TablaInsertada("clientes", 3)), 0.1));
        sesion.setAttribute("bbdd.analisis", new AnalisisBbdd(true, List.of(), "mia",
                List.of(new TablaAnalizada("clientes", 3, -1, 3, 1, 1)), 0.05));
        sesion.setAttribute("bbdd.exportacion", new ExportacionBbdd(true, List.of(), "mia", DUMP_MIA, 900, REGISTRADA, 0.2));
        return sesion;
    }

    // --- Acceso a las páginas ---

    @Test
    @WithMockUser(roles = "ANALYST")
    // El analista entra en BBDD, análisis y logs, pero no puede probar el otro servidor ni restaurar (paso 9).
    void analistaSinPaso9() throws Exception {
        mvc.perform(get("/bbdd")).andExpect(status().isOk());
        mvc.perform(get("/analisis")).andExpect(status().isOk());
        mvc.perform(get("/logs")).andExpect(status().isOk());
        mvc.perform(post("/bbdd/servidor/probar").with(csrf()).session(exportada())).andExpect(status().isForbidden());
        mvc.perform(post("/bbdd/restaurar").with(csrf()).session(exportada())).andExpect(status().isForbidden());
        verify(api, never()).probarServidor(any());
        verify(api, never()).restaurarBbdd(anyString(), anyString(), any());
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // El usuario normal entra en BBDD, análisis y logs, pero no en usuarios ni paso 9.
    void usuarioSinUsuariosNiPaso9() throws Exception {
        mvc.perform(get("/bbdd")).andExpect(status().isOk());
        mvc.perform(get("/analisis")).andExpect(status().isOk());
        mvc.perform(get("/logs")).andExpect(status().isOk());
        mvc.perform(get("/usuarios")).andExpect(status().isForbidden());
        mvc.perform(post("/bbdd/restaurar").with(csrf()).session(exportada())).andExpect(status().isForbidden());
        verify(api, never()).restaurarBbdd(anyString(), anyString(), any());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    // El administrador sí llega al paso 9 (sin exportar, el controlador le pide antes el paso 8).
    void adminConPaso9() throws Exception {
        mvc.perform(post("/bbdd/restaurar").with(csrf())
                        .param("host", "192.168.1.57").param("puerto", "5432").param("usuario", "ana"))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", "Primero exporta la base de datos (paso 8)."));
    }

    // --- Lo que se ve en la pantalla ---

    @Test
    @WithMockUser(roles = "ADMIN")
    // El administrador ve el paso 9 y todas las BBDD del registro.
    void adminVePaso9YTodoElRegistro() throws Exception {
        mvc.perform(get("/bbdd").session(exportada()))
           .andExpect(content().string(containsString("9. Restaurar en otro servidor")))
           .andExpect(content().string(containsString("Restaurar en otro servidor (opcional)")))
           .andExpect(content().string(containsString(DUMP_AJENA)))
           .andExpect(content().string(containsString("antigua_20261101_090000.sql")));
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    // El analista ve todas las BBDD del registro, pero no el paso 9.
    void analistaVeTodoElRegistroSinPaso9() throws Exception {
        mvc.perform(get("/bbdd").session(exportada()))
           .andExpect(content().string(not(containsString("9. Restaurar en otro servidor"))))
           .andExpect(content().string(not(containsString("Restaurar en otro servidor (opcional)"))))
           .andExpect(content().string(containsString(DUMP_MIA)))
           .andExpect(content().string(containsString(DUMP_AJENA)))
           .andExpect(content().string(containsString("antigua_20261101_090000.sql")));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // El usuario normal solo ve sus BBDD en el registro (ni las de otros ni las que no tienen propietario), sin paso 9.
    void usuarioSoloVeSusBbdd() throws Exception {
        mvc.perform(get("/bbdd").session(exportada()))
           .andExpect(content().string(not(containsString("9. Restaurar en otro servidor"))))
           .andExpect(content().string(containsString(DUMP_MIA)))
           .andExpect(content().string(not(containsString(DUMP_AJENA))))
           .andExpect(content().string(not(containsString("antigua_20261101_090000.sql"))));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // El menú y el inicio enseñan los logs al usuario normal, pero no la gestión de usuarios.
    void usuarioVeLosLogsEnElMenu() throws Exception {
        mvc.perform(get("/"))
           .andExpect(content().string(containsString("href=\"/logs\"")))
           .andExpect(content().string(not(containsString("href=\"/usuarios\""))))
           .andExpect(content().string(containsString("<span class=\"user-role\">Usuario</span>")));
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // El usuario normal puede subir un fichero de logs.
    void usuarioSubeLogs() throws Exception {
        var txt = new org.springframework.mock.web.MockMultipartFile("fichero", "hibernate.txt", "text/plain",
                "select 1".getBytes());
        mvc.perform(multipart("/logs").file(txt).with(csrf()))
           .andExpect(redirectedUrl("/logs"))
           .andExpect(flash().attributeExists("aviso"));
    }

    // --- Descarga de dumps ---

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // El usuario normal descarga sus dumps; los de otros (o sin propietario) dan 404 y ni se piden a la API.
    void usuarioSoloDescargaSusDumps() throws Exception {
        mvc.perform(get("/bbdd/dumps/" + DUMP_MIA)).andExpect(status().isOk());
        mvc.perform(get("/bbdd/dumps/" + DUMP_AJENA)).andExpect(status().isNotFound());
        mvc.perform(get("/bbdd/dumps/antigua_20261101_090000.sql")).andExpect(status().isNotFound());
        verify(api).descargarDump(eq(DUMP_MIA), any());
        verify(api, never()).descargarDump(eq(DUMP_AJENA), any());
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    // El analista descarga cualquier dump.
    void analistaDescargaCualquierDump() throws Exception {
        mvc.perform(get("/bbdd/dumps/" + DUMP_AJENA)).andExpect(status().isOk());
        mvc.perform(get("/bbdd/dumps/antigua_20261101_090000.sql")).andExpect(status().isOk());
    }

    // --- Propietario ---

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // Al crear la BBDD (paso 5) queda apuntada como del usuario conectado.
    void crearApuntaElPropietario() throws Exception {
        when(api.crearBbdd(eq("nueva"), eq(DDL), anyMap())).thenReturn(creada("nueva"));

        mvc.perform(post("/bbdd/crear").with(csrf()).session(conPrototipo("nueva"))).andExpect(redirectedUrl("/bbdd#creacion"));

        assertThat(propietarios.findByNombre("nueva")).get().extracting(BbddPropietario::getUsername).isEqualTo("pepe");
    }

    @Test
    @WithMockUser(username = "pepe", roles = "USUARIO")
    // El reloj de la carga no da el progreso de una BBDD ajena.
    void progresoSoloDeSusBbdd() throws Exception {
        var sesion = exportada();
        ((CreacionBbddForm) sesion.getAttribute("bbdd.form")).setNombreBbdd("ajena");
        mvc.perform(get("/bbdd/insertar/progreso").session(sesion)).andExpect(status().isNoContent());
        verify(api, never()).progresoInsercion(anyString());
    }
}
