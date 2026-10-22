package es.tfg.sqlanalyzer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class UsuarioTests {

    @Autowired
    MockMvc mvc;

    @Test
    // Verifica que la página de registro es accesible públicamente, permite crear una nueva cuenta y que el nuevo usuario puede iniciar sesión correctamente.
    void registroEsPublicoYCreaCuenta() throws Exception {
        mvc.perform(get("/registro")).andExpect(status().isOk());

        mvc.perform(post("/registro").with(csrf())
                .param("username", "nuevo_analista")
                .param("password", "secreto1")
                .param("confirmPassword", "secreto1"))
           .andExpect(redirectedUrl("/login"));

        mvc.perform(formLogin("/login").user("nuevo_analista").password("secreto1"))
           .andExpect(redirectedUrl("/"));
    }

    @Test
    // Verifica que el registro rechaza contraseñas distintas y usuarios duplicados.
    void registroRechazaContrasenasDistintasYUsuarioDuplicado() throws Exception {
        mvc.perform(post("/registro").with(csrf())
                .param("username", "otro_usuario")
                .param("password", "secreto1")
                .param("confirmPassword", "no-coincide"))
           .andExpect(status().isOk())
           .andExpect(model().attributeHasFieldErrors("form", "confirmPassword"));

        mvc.perform(post("/registro").with(csrf())
                .param("username", "admin")
                .param("password", "secreto1")
                .param("confirmPassword", "secreto1"))
           .andExpect(status().isOk())
           .andExpect(model().attributeHasFieldErrors("form", "username"));
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    // Verifica que un usuario con rol ANALYST no puede acceder a la página de gestión de usuarios (acceso denegado).
    void analistaNoAccedeAUsuarios() throws Exception {
        mvc.perform(get("/usuarios")).andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    // Verifica que un usuario con rol ADMIN puede acceder a la página de gestión de usuarios, crear un nuevo usuario y que el nuevo usuario puede iniciar sesión correctamente.
    void adminGestionaUsuariosCrud() throws Exception {
        mvc.perform(get("/usuarios")).andExpect(status().isOk());

        mvc.perform(post("/usuarios").with(csrf())
                .param("username", "temporal")
                .param("password", "secreto1")
                .param("rol", "ANALYST")
                .param("habilitado", "true"))
           .andExpect(redirectedUrl("/usuarios"));

        mvc.perform(formLogin("/login").user("temporal").password("secreto1"))
           .andExpect(redirectedUrl("/"));
    }
}
