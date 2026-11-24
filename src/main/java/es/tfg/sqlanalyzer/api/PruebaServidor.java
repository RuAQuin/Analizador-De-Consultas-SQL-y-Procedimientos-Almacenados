package es.tfg.sqlanalyzer.api;

import java.util.List;

/**
 * Resultado de «Probar conexión» con el PostgreSQL de otro equipo: si la API llega al servidor y el usuario
 * puede crear bases de datos. Si no, errores dice por qué y qué revisar.
 */
public record PruebaServidor(boolean valido,
                             List<ErrorDdl> errores,
                             // «host:puerto» con el que se ha conectado la API.
                             String servidor,
                             // Versión de PostgreSQL del servidor.
                             String version) {
}
