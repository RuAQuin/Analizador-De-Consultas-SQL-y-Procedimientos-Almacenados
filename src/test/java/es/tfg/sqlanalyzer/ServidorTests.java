package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.BbddRegistrada;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.ExportacionBbdd;
import es.tfg.sqlanalyzer.api.PruebaServidor;
import es.tfg.sqlanalyzer.api.RestauracionBbdd;
import es.tfg.sqlanalyzer.api.Servidor;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import es.tfg.sqlanalyzer.form.CreacionBbddForm;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.time.OffsetDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
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

/** Módulo 1, paso 9: restaurar el respaldo del paso 8 en el PostgreSQL de otro equipo, con la API simulada. */
@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser(roles = "ADMIN")
class ServidorTests {

    private static final String DDL = "CREATE TABLE clientes (id integer PRIMARY KEY);";
    private static final String DUMP = "tienda_20261124_101500.dump";
    private static final Servidor OTRO = new Servidor("192.168.1.57", 5433, "ana", "secreta");

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ApiPythonClient api;

    @BeforeEach
    void registroVacio() {
        when(api.listarRegistro()).thenReturn(List.of());
    }

    // Sesión con la BBDD ya exportada (paso 8).
    private static MockHttpSession exportada() {
        var sesion = new MockHttpSession();
        var form = new CreacionBbddForm();
        form.setNombreBbdd("tienda");
        form.setDefinicionTablas(DDL);
        sesion.setAttribute("bbdd.form", form);
        sesion.setAttribute("bbdd.validacion", new ValidacionDdl(true, List.of("clientes"), List.of(), List.of(),
                List.of(new TablaOrdenada("clientes", 0)), List.of(), List.of()));
        sesion.setAttribute("bbdd.exportacion", new ExportacionBbdd(true, List.of(), "tienda", DUMP, 900,
                OffsetDateTime.parse("2026-11-24T10:15:00Z"), 0.2));
        return sesion;
    }

    private static MockHttpServletRequestBuilder conServidor(MockHttpServletRequestBuilder peticion, String contrasena) {
        return peticion.with(csrf()).param("host", OTRO.host()).param("puerto", String.valueOf(OTRO.puerto()))
                .param("usuario", OTRO.usuario()).param("contrasena", contrasena);
    }

    private static RestauracionBbdd restaurada() {
        return new RestauracionBbdd(true, List.of(), "tienda", "192.168.1.57:5433", "17.6", DUMP,
                List.of(new RestauracionBbdd.Tabla("clientes", 3), new RestauracionBbdd.Tabla("compras", 7)), 0.8);
    }

    @Test
    // Tras exportar aparece el paso 9, vacío.
    void trasExportarApareceElPaso9() throws Exception {
        mvc.perform(get("/bbdd").session(exportada()))
           .andExpect(content().string(containsString("9. Restaurar en otro servidor")))
           .andExpect(content().string(containsString("Restaurar en ese servidor")))
           .andExpect(content().string(containsString("value=\"5432\"")));
    }

    @Test
    // Sin exportar no aparece el paso 9 ni se puede restaurar.
    void sinExportarNoSePuedeRestaurar() throws Exception {
        var sesion = exportada();
        sesion.removeAttribute("bbdd.exportacion");
        mvc.perform(get("/bbdd").session(sesion))
           .andExpect(content().string(not(containsString("9. Restaurar en otro servidor"))));
        mvc.perform(conServidor(post("/bbdd/restaurar"), "secreta").session(sesion))
           .andExpect(redirectedUrl("/bbdd"))
           .andExpect(flash().attribute("error", "Primero exporta la base de datos (paso 8)."));
        verify(api, never()).restaurarBbdd(anyString(), anyString(), any());
    }

    @Test
    // Restaurar envía a la API la BBDD, su respaldo y el servidor; se muestra el resultado.
    void restaurarEnviaElRespaldoYElServidor() throws Exception {
        var sesion = exportada();
        when(api.restaurarBbdd("tienda", DUMP, OTRO)).thenReturn(restaurada());
        mvc.perform(conServidor(post("/bbdd/restaurar"), "secreta").session(sesion))
           .andExpect(redirectedUrl("/bbdd#restauracion"))
           .andExpect(flash().attribute("aviso", containsString("«tienda» en 192.168.1.57:5433 (PostgreSQL 17.6): 2 tablas y 10 filas")));
        mvc.perform(get("/bbdd").session(sesion))
           .andExpect(content().string(containsString("Última restauración")))
           .andExpect(content().string(containsString("docker exec -it sqlanalyzer-api psql -h 192.168.1.57 -p 5433 -U ana -d tienda")))
           // Se recuerdan host, puerto y usuario, pero nunca se escribe la contraseña en la página.
           .andExpect(content().string(containsString("value=\"192.168.1.57\"")))
           .andExpect(content().string(containsString("(la ya indicada)")))
           .andExpect(content().string(not(containsString("secreta"))));
    }

    @Test
    // Si falla (por ejemplo, ya existe en ese servidor), se muestra el motivo y se puede reintentar.
    void restaurarConError() throws Exception {
        when(api.restaurarBbdd("tienda", DUMP, OTRO)).thenReturn(new RestauracionBbdd(false, List.of(new ErrorDdl(
                "Ya existe una base de datos «tienda» en 192.168.1.57:5433: bórrala antes o restaura en otro servidor",
                null, null)), null, null, null, null, List.of(), 0));
        mvc.perform(conServidor(post("/bbdd/restaurar"), "secreta").session(exportada()))
           .andExpect(view().name("bbdd"))
           .andExpect(content().string(containsString("No se ha restaurado la base de datos")))
           .andExpect(content().string(containsString("Ya existe una base de datos «tienda» en 192.168.1.57:5433")));
    }

    @Test
    // Sin host ni usuario no se llama a la API.
    void elServidorSeValida() throws Exception {
        mvc.perform(post("/bbdd/restaurar").with(csrf()).session(exportada()).param("puerto", "5432"))
           .andExpect(view().name("bbdd"))
           .andExpect(content().string(containsString("Indica el host (IP o nombre) del equipo con PostgreSQL")))
           .andExpect(content().string(containsString("Indica el usuario de PostgreSQL de ese servidor")));
        verify(api, never()).restaurarBbdd(anyString(), anyString(), any());
    }

    @Test
    // «Probar conexión» correcta: se muestra la versión y se recuerda la contraseña para restaurar sin repetirla.
    void probarYRestaurarSinRepetirLaContrasena() throws Exception {
        var sesion = exportada();
        when(api.probarServidor(OTRO)).thenReturn(new PruebaServidor(true, List.of(), "192.168.1.57:5433", "17.6"));
        mvc.perform(conServidor(post("/bbdd/servidor/probar"), "secreta").session(sesion))
           .andExpect(view().name("bbdd"))
           .andExpect(content().string(containsString("Conexión correcta con 192.168.1.57:5433 (PostgreSQL 17.6)")))
           .andExpect(content().string(not(containsString("secreta"))));

        when(api.restaurarBbdd("tienda", DUMP, OTRO)).thenReturn(restaurada());
        mvc.perform(conServidor(post("/bbdd/restaurar"), "").session(sesion)).andExpect(redirectedUrl("/bbdd#restauracion"));
        verify(api).restaurarBbdd("tienda", DUMP, OTRO); // Con la contraseña de la prueba.
    }

    @Test
    // «Probar conexión» fallida: se muestra el motivo que da la API.
    void probarConexionFallida() throws Exception {
        when(api.probarServidor(any())).thenReturn(new PruebaServidor(false, List.of(new ErrorDdl(
                "No se ha podido conectar con PostgreSQL (192.168.1.57:5433): Connection refused. Posible causa: el servidor"
                        + " no responde", null, null)), "192.168.1.57:5433", null));
        mvc.perform(conServidor(post("/bbdd/servidor/probar"), "secreta").session(exportada()))
           .andExpect(view().name("bbdd"))
           .andExpect(content().string(containsString("Posible causa: el servidor no responde")));
    }

    @Test
    // Un DDL nuevo olvida la restauración anterior (era de otra BBDD).
    void unDdlNuevoOlvidaLaRestauracion() throws Exception {
        var sesion = exportada();
        sesion.setAttribute("bbdd.restauracion", restaurada());
        when(api.validarDdl(DDL)).thenReturn(new ValidacionDdl(true, List.of("clientes"), List.of(), List.of(),
                List.of(new TablaOrdenada("clientes", 0)), List.of(), List.of()));
        mvc.perform(post("/bbdd").with(csrf()).session(sesion).param("nombreBbdd", "otra").param("definicionTablas", DDL))
           .andExpect(redirectedUrl("/bbdd"));
        assertThat(sesion.getAttribute("bbdd.restauracion")).isNull();
    }

    @Test
    // En el registro se ve el servidor de cada BBDD y la contraseña nunca aparece al mostrar un servidor.
    void registroYServidor() {
        var copia = new BbddRegistrada("tienda", 1, 3, DUMP, 900, OffsetDateTime.parse("2026-11-24T10:15:00Z"), null,
                "192.168.1.57:5433");
        var propia = new BbddRegistrada("tienda", 1, 3, DUMP, 900, OffsetDateTime.parse("2026-11-24T10:15:00Z"), true, "");
        assertThat(copia.donde()).isEqualTo("192.168.1.57:5433");
        assertThat(propia.donde()).isEqualTo("Aplicación");
        assertThat(OTRO.toString()).doesNotContain("secreta").contains("ana@192.168.1.57:5433");
    }
}
