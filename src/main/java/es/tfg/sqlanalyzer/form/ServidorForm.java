package es.tfg.sqlanalyzer.form;

import es.tfg.sqlanalyzer.api.Servidor;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;

/**
 * Paso 9 del módulo 1: PostgreSQL de otro equipo de la red donde se restaura la BBDD.
 * La contraseña no se vuelve a mostrar en la página y solo se guarda en la sesión.
 */
@Getter
@Setter
public class ServidorForm {

    /** Puerto por defecto de PostgreSQL. */
    public static final int PUERTO_POR_DEFECTO = 5432;

    @NotBlank(message = "Indica el host (IP o nombre) del equipo con PostgreSQL")
    @Size(max = 255, message = "El host es demasiado largo")
    // IP (IPv4 o IPv6).
    private String host;

    @NotNull(message = "Indica el puerto")
    @Min(value = 1, message = "El puerto debe estar entre 1 y 65535")
    @Max(value = 65535, message = "El puerto debe estar entre 1 y 65535")
    // 5432 por defecto, pero puede ser otro.
    private Integer puerto = PUERTO_POR_DEFECTO;

    @NotBlank(message = "Indica el usuario de PostgreSQL de ese servidor")
    @Size(max = 63, message = "El usuario es demasiado largo")
    // Usuario de PostgreSQL (no del sistema operativo) que puede crear bases de datos.
    private String usuario;

    @Size(max = 200, message = "La contraseña es demasiado larga")
    // Contraseña de ese usuario de PostgreSQL. No se guarda en la BBDD propia (H2), solo en la sesión.
    private String contrasena;

    /** Servidor para la API. */
    public Servidor servidor() {
        return new Servidor(host.strip(), puerto, usuario.strip(), contrasena == null ? "" : contrasena);
    }

    /** Formulario con los datos de un servidor ya usado, sin la contraseña (no se vuelve a mostrar). */
    public static ServidorForm de(Servidor servidor) {
        ServidorForm form = new ServidorForm();
        if (servidor != null) {
            form.setHost(servidor.host());
            form.setPuerto(servidor.puerto());
            form.setUsuario(servidor.usuario());
        }
        return form;
    }
}
