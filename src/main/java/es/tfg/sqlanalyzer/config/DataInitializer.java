package es.tfg.sqlanalyzer.config;

import es.tfg.sqlanalyzer.model.Rol;
import es.tfg.sqlanalyzer.model.Usuario;
import es.tfg.sqlanalyzer.repository.UsuarioRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * Siembra los usuarios iniciales (admin/analista) la primera vez que arranca
 * la aplicación, cuando la tabla de usuarios todavía está vacía.
 */
@Component
public class DataInitializer implements ApplicationRunner {

    private final UsuarioRepository repo;
    private final PasswordEncoder encoder;
    private final JdbcTemplate jdbc;
    private final String adminUsername;
    private final String adminPassword;
    private final String analystUsername;
    private final String analystPassword;

    // Constructor que inyecta las dependencias necesarias y los valores de configuración para los usuarios iniciales.
    public DataInitializer(
            UsuarioRepository repo,
            PasswordEncoder encoder,
            JdbcTemplate jdbc,
            @Value("${app.security.admin.username:admin}") String adminUsername,
            @Value("${app.security.admin.password:admin123}") String adminPassword,
            @Value("${app.security.analyst.username:analista}") String analystUsername,
            @Value("${app.security.analyst.password:analista123}") String analystPassword) {
        this.repo = repo;
        this.encoder = encoder;
        this.jdbc = jdbc;
        this.adminUsername = adminUsername;
        this.adminPassword = adminPassword;
        this.analystUsername = analystUsername;
        this.analystPassword = analystPassword;
    }

    @Override
    // Método que se ejecuta al iniciar la aplicación. Si la tabla de usuarios está vacía, crea los usuarios iniciales (admin y analista).
    public void run(ApplicationArguments args) {
        adaptarColumnaRol();
        if (repo.count() == 0) {
            repo.save(nuevoUsuario(adminUsername, adminPassword, Rol.ADMIN));
            repo.save(nuevoUsuario(analystUsername, analystPassword, Rol.ANALYST));
        }
    }

    // Las BBDD H2 creadas antes del rol USUARIO tienen la columna rol como ENUM('ADMIN','ANALYST') de H2, que
    // ddl-auto=update no cambia: se pasa a VARCHAR(20) (los valores se conservan) para que acepte el rol nuevo.
    private void adaptarColumnaRol() {
        List<String> tipo = jdbc.queryForList("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS"
                + " WHERE TABLE_NAME = 'USUARIOS' AND COLUMN_NAME = 'ROL'", String.class);
        if (tipo.contains("ENUM")) {
            jdbc.execute("ALTER TABLE usuarios ALTER COLUMN rol SET DATA TYPE VARCHAR(20)");
        }
    }

    // Método privado para crear un nuevo usuario con los parámetros especificados.
    private Usuario nuevoUsuario(String username, String rawPassword, Rol rol) {
        Usuario usuario = new Usuario();
        usuario.setUsername(username);
        usuario.setPassword(encoder.encode(rawPassword));
        usuario.setRol(rol);
        usuario.setHabilitado(true);
        return usuario;
    }
}
