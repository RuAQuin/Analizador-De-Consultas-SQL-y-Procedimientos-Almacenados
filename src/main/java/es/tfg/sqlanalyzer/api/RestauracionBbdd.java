package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/**
 * Respuesta de la API al paso 9: el respaldo del paso 8 restaurado (pg_restore) y analizado en el PostgreSQL
 * de otro equipo. Si no es válida, errores dice por qué y en ese servidor no se ha dejado nada.
 */
public record RestauracionBbdd(boolean valido,
                               List<ErrorDdl> errores,
                               String bbdd,
                               // «host:puerto» del otro servidor.
                               String servidor,
                               // Versión de PostgreSQL del otro servidor.
                               String version,
                               // Respaldo restaurado.
                               String fichero,
                               // Filas de cada tabla tras el ANALYZE en el otro servidor.
                               List<Tabla> tablas,
                               double segundos) implements Serializable {

    public record Tabla(String tabla, long filas) implements Serializable {
    }

    /** Filas restauradas en total. */
    public long totalFilas() {
        return tablas.stream().mapToLong(Tabla::filas).sum();
    }
}
