package es.tfg.sqlanalyzer.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

/**
 * Configuración de Spring Security.
 *
 * Roles:
 *  - ADMIN   : acceso completo (todas las BBDD, paso 9, análisis, logs y gestión de usuarios).
 *  - ANALYST : todas las BBDD, análisis de consultas y logs (sin paso 9 ni gestión de usuarios).
 *  - USUARIO : solo sus BBDD (las que ha creado), análisis de consultas y logs (sin paso 9 ni gestión de usuarios).
 *
 * Los usuarios se persisten en la BBDD propia (H2) a través de
 * {@link es.tfg.sqlanalyzer.security.UsuarioDetailsService}; el alta inicial
 * se siembra desde application.properties / variables de entorno.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    // Configuración de la cadena de filtros de seguridad. Define las reglas de autorización, la página de login, la gestión de sesiones y las cabeceras HTTP.
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/css/**", "/js/**", "/img/**", "/favicon.ico", "/error").permitAll()
                .requestMatchers("/login", "/registro").permitAll()
                .requestMatchers("/usuarios/**").hasRole("ADMIN")
                // Paso 9 (probar el otro servidor y restaurar): solo ADMIN. Antes que /bbdd/** (gana la primera regla).
                .requestMatchers("/bbdd/servidor/**", "/bbdd/restaurar").hasRole("ADMIN")
                // Los tres roles. USUARIO solo ve y usa sus BBDD (PermisosBbdd).
                .requestMatchers("/bbdd/**", "/analisis/**", "/logs/**").hasAnyRole("ADMIN", "ANALYST", "USUARIO")
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/", true)
                .failureUrl("/login?error")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .deleteCookies("JSESSIONID")
                .permitAll()
            )
            // Página de acceso denegado personalizada. Se muestra cuando un usuario intenta acceder a un recurso para el que no tiene permisos.
            .exceptionHandling(ex -> ex.accessDeniedPage("/acceso-denegado"))
            .sessionManagement(session -> session
                .sessionFixation(fix -> fix.migrateSession())
            )
            // Cabeceras HTTP de seguridad.
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'"))
                .referrerPolicy(ref -> ref.policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.SAME_ORIGIN))
            );
        // CSRF activo por defecto: para generar un valor aleatorio y único para cada sesión, que se debe enviar en cada petición POST, PUT, DELETE, etc.
        return http.build();
    }

    @Bean
    // Bean que proporciona un codificador de contraseñas utilizando el algoritmo BCrypt. Este codificador se utiliza para almacenar las contraseñas de los usuarios de forma segura en la base de datos.
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
