package es.tfg.sqlanalyzer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    // Verifica que un usuario anónimo es redirigido a la página de login al intentar acceder a la raíz de la aplicación.
    void anonimoRedirigeALogin() throws Exception {
        mvc.perform(get("/")).andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    // Verifica que la página de login es accesible públicamente y devuelve un estado HTTP 200 OK.
    void loginPublico() throws Exception {
        mvc.perform(get("/login")).andExpect(status().isOk());
    }

    @Test
    // Verifica que un usuario con credenciales correctas es redirigido a la raíz de la aplicación, mientras que un usuario con credenciales incorrectas es redirigido a la página de login con un parámetro de error.
    void loginCorrectoYIncorrecto() throws Exception {
        mvc.perform(formLogin("/login").user("admin").password("admin123"))
           .andExpect(redirectedUrl("/"));
        mvc.perform(formLogin("/login").user("admin").password("mal"))
           .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    // Verifica que un usuario con rol ANALYST puede acceder a las páginas de base de datos, análisis y logs, pero no puede acceder a la página de usuarios (acceso denegado).
    void analistaAccedeABbddPeroNoAUsuarios() throws Exception {
        mvc.perform(get("/bbdd")).andExpect(status().isOk());
        mvc.perform(get("/analisis")).andExpect(status().isOk());
        mvc.perform(get("/logs")).andExpect(status().isOk());
        mvc.perform(get("/usuarios")).andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    // Verifica que un usuario con rol ADMIN puede acceder a todas las páginas de la aplicación (base de datos, análisis, logs y usuarios).
    void adminAccedeATodo() throws Exception {
        mvc.perform(get("/bbdd")).andExpect(status().isOk());
        mvc.perform(get("/analisis")).andExpect(status().isOk());
        mvc.perform(get("/logs")).andExpect(status().isOk());
        mvc.perform(get("/usuarios")).andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    // Verifica que una petición POST sin token CSRF es rechazada con un estado HTTP 403 Forbidden.
    void postSinCsrfRechazado() throws Exception {
        //Falta CSRF token
        mvc.perform(post("/analisis").param("sql", "SELECT 1"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    // Verifica que los formularios de creación de base de datos y análisis validan correctamente los campos requeridos y redirigen a la página de análisis después de un envío exitoso.
    void formulariosValidan() throws Exception {
        // Incluyen CSRF token
        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "Mal Nombre"))
           .andExpect(status().isOk())
           .andExpect(model().attributeHasFieldErrors("form", "nombreBbdd", "definicionTablas"));

        mvc.perform(post("/analisis").with(csrf())
                .param("sql", "SELECT 1").param("tipo", "CONSULTA").param("explainPlan", "true"))
           .andExpect(redirectedUrl("/analisis"));
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    // Verifica que la subida de logs valida correctamente el tipo de archivo y redirige a la página de logs con un mensaje de aviso o error según corresponda.
    void subidaLogs() throws Exception {
        var txt = new MockMultipartFile("fichero", "hibernate.txt", "text/plain", "select 1".getBytes());
        mvc.perform(multipart("/logs").file(txt).with(csrf()))
           .andExpect(redirectedUrl("/logs"))
           .andExpect(flash().attributeExists("aviso"));

        var pdf = new MockMultipartFile("fichero", "logs.pdf", "application/pdf", "x".getBytes());
        mvc.perform(multipart("/logs").file(pdf).with(csrf()))
           .andExpect(flash().attributeExists("error"));
    }
}
