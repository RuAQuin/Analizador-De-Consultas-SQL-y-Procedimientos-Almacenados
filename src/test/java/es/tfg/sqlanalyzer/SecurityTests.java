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
    void anonimoRedirigeALogin() throws Exception {
        mvc.perform(get("/")).andExpect(status().is3xxRedirection())
           .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void loginPublico() throws Exception {
        mvc.perform(get("/login")).andExpect(status().isOk());
    }

    @Test
    void loginCorrectoYIncorrecto() throws Exception {
        mvc.perform(formLogin("/login").user("admin").password("admin123"))
           .andExpect(redirectedUrl("/"));
        mvc.perform(formLogin("/login").user("admin").password("mal"))
           .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    void analistaAccedeABbddPeroNoAUsuarios() throws Exception {
        mvc.perform(get("/bbdd")).andExpect(status().isOk());
        mvc.perform(get("/analisis")).andExpect(status().isOk());
        mvc.perform(get("/logs")).andExpect(status().isOk());
        mvc.perform(get("/usuarios")).andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminAccedeATodo() throws Exception {
        mvc.perform(get("/bbdd")).andExpect(status().isOk());
        mvc.perform(get("/analisis")).andExpect(status().isOk());
        mvc.perform(get("/logs")).andExpect(status().isOk());
        mvc.perform(get("/usuarios")).andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void postSinCsrfRechazado() throws Exception {
        mvc.perform(post("/analisis").param("sql", "SELECT 1"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void formulariosValidan() throws Exception {
        mvc.perform(post("/bbdd").with(csrf()).param("nombreBbdd", "Mal Nombre"))
           .andExpect(status().isOk())
           .andExpect(model().attributeHasFieldErrors("form", "nombreBbdd", "definicionTablas"));

        mvc.perform(post("/analisis").with(csrf())
                .param("sql", "SELECT 1").param("tipo", "CONSULTA").param("explainPlan", "true"))
           .andExpect(redirectedUrl("/analisis"));
    }

    @Test
    @WithMockUser(roles = "ANALYST")
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
