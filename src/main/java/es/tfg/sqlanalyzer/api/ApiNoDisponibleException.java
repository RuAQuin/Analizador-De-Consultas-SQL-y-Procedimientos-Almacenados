package es.tfg.sqlanalyzer.api;

/** La API Python no responde o devuelve una respuesta inesperada. */
public class ApiNoDisponibleException extends RuntimeException {

    public ApiNoDisponibleException(String mensaje, Throwable causa) {
        super(mensaje, causa);
    }
}
