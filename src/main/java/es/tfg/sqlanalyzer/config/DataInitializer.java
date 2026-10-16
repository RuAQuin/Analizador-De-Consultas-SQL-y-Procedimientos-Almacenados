package es.tfg.sqlanalyzer.config;

import es.tfg.sqlanalyzer.model.Rol;
import es.tfg.sqlanalyzer.model.Usuario;
import es.tfg.sqlanalyzer.repository.UsuarioRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * Siembra los usuarios iniciales (admin/analista) la primera vez que arranca
 * la aplicación, cuando la tabla de usuarios todavía está vacía.
 */
@Component
public class DataInitializer implements ApplicationRunner {

    private final UsuarioRepository repo;
    private final PasswordEncoder encoder;
    private final String adminUsername;
    private final String adminPassword;
    private final String analystUsername;
    private final String analystPassword;

    public DataInitializer(
            UsuarioRepository repo,
            PasswordEncoder encoder,
            @Value("${app.security.admin.username:admin}") String adminUsername,
            @Value("${app.security.admin.password:admin123}") String adminPassword,
            @Value("${app.security.analyst.username:analista}") String analystUsername,
            @Value("${app.security.analyst.password:analista123}") String analystPassword) {
        this.repo = repo;
        this.encoder = encoder;
        this.adminUsername = adminUsername;
        this.adminPassword = adminPassword;
        this.analystUsername = analystUsername;
        this.analystPassword = analystPassword;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (repo.count() == 0) {
            repo.save(nuevoUsuario(adminUsername, adminPassword, Rol.ADMIN));
            repo.save(nuevoUsuario(analystUsername, analystPassword, Rol.ANALYST));
        }
    }

    private Usuario nuevoUsuario(String username, String rawPassword, Rol rol) {
        Usuario usuario = new Usuario();
        usuario.setUsername(username);
        usuario.setPassword(encoder.encode(rawPassword));
        usuario.setRol(rol);
        usuario.setHabilitado(true);
        return usuario;
    }
}
