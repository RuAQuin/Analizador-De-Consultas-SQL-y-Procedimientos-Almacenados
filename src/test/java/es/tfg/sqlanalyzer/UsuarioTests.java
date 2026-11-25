package es.tfg.sqlanalyzer;

import es.tfg.sqlanalyzer.model.BbddPropietario;
import es.tfg.sqlanalyzer.model.Rol;
import es.tfg.sqlanalyzer.model.Usuario;
import es.tfg.sqlanalyzer.repository.BbddPropietarioRepository;
import es.tfg.sqlanalyzer.repository.UsuarioRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class UsuarioTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    UsuarioRepository usuarios;

    @Autowired
    BbddPropietarioRepository propietarios;

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
        // El autorregistro da el rol USUARIO (solo sus BBDD), no ANALYST.
        assertThat(usuarios.findByUsername("nuevo_analista")).get().extracting(Usuario::getRol).isEqualTo(Rol.USUARIO);
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    // Si el administrador renombra a un usuario, sus BBDD pasan al nombre nuevo; si lo elimina, quedan sin propietario.
    void renombrarYEliminarMuevenSusBbdd() throws Exception {
        // Crear un usuario y una BBDD asociada.
        mvc.perform(post("/usuarios").with(csrf())
                .param("username", "dueno").param("password", "secreto1")
                .param("rol", "USUARIO").param("habilitado", "true"))
           .andExpect(redirectedUrl("/usuarios"));
        Long id = usuarios.findByUsername("dueno").orElseThrow().getId();
        propietarios.save(new BbddPropietario("bbdd_de_dueno", "dueno"));

        // Renombrar el usuario y verificar que sus BBDD se actualizan.
        mvc.perform(post("/usuarios/" + id).with(csrf())
                .param("username", "dueno2").param("password", "")
                .param("rol", "USUARIO").param("habilitado", "true"))
           .andExpect(redirectedUrl("/usuarios"));
        assertThat(propietarios.existsByNombreAndUsername("bbdd_de_dueno", "dueno2")).isTrue();

        // Eliminar el usuario y verificar que sus BBDD quedan sin propietario.
        mvc.perform(post("/usuarios/" + id + "/eliminar").with(csrf())).andExpect(redirectedUrl("/usuarios"));
        assertThat(propietarios.findByNombre("bbdd_de_dueno")).isEmpty();
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
