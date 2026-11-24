package es.tfg.sqlanalyzer.api;

import java.io.Serializable;

/**
 * PostgreSQL de otro equipo de la red donde se crea la BBDD (módulo 1). Se envía a la API en cada petición;
 * la contraseña solo se guarda en la sesión del usuario, nunca en la BBDD propia (H2).
 */
public record Servidor(String host, int puerto, String usuario, String contrasena) implements Serializable {

    /** «host:puerto», para mostrarlo. */
    public String descripcion() {
        return host + ":" + puerto;
    }

    /** Sin la contraseña: así no aparece nunca en los registros (logs) ni en las trazas de error. */
    @Override
    public String toString() {
        return "Servidor[" + usuario + "@" + descripcion() + "]";
    }
}
