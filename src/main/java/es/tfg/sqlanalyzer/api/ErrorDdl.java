package es.tfg.sqlanalyzer.api;

/** Error devuelto por la API al parsear el DDL. Línea y columna pueden ser nulas. */
public record ErrorDdl(String mensaje, Integer linea, Integer columna) {

    /** Texto para mostrar en la pantalla, con la posición si se conoce. */
    public String descripcion() {
        if (linea == null) {
            return mensaje;
        }
        return "Línea " + linea + (columna != null ? ", columna " + columna : "") + ": " + mensaje;
    }
}
