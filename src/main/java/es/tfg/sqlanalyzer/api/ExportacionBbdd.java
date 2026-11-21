package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;

/**
 * Respuesta de la API al paso 8: respaldo con pg_dump en formato custom (8.1) y registro como BBDD objetivo
 * en el repositorio (8.2). Si no es válida, errores dice por qué (por ejemplo, que falta el ANALYZE) y no se ha
 * guardado ningún dump.
 */
public record ExportacionBbdd(boolean valido, // Si no es válida, lista de errores DDL que la invalidan.
                              List<ErrorDdl> errores,
                              String bbdd,
                              // Fichero del dump: se descarga con GET /bbdd/dumps/{fichero}.
                              String fichero,
                              long bytes,
                              // Momento del registro en el repositorio.
                              OffsetDateTime registrada,
                              double segundos) implements Serializable {

    /** Tamaño del dump legible (KB, MB...). */
    public String tamano() {
        return Tamanos.legible(bytes);
    }

    /** Momento del registro en la zona horaria del equipo (PostgreSQL lo da en UTC). */
    public LocalDateTime registradaLocal() {
        return registrada == null ? null : registrada.atZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime();
    }
}
