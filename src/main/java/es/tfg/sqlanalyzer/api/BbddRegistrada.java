package es.tfg.sqlanalyzer.api;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.io.Serializable;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;

/** BBDD objetivo registrada en el repositorio (paso 8.2). */
public record BbddRegistrada(String nombre,
                             int tablas,
                             @JsonProperty("total_filas") long totalFilas,
                             // Último dump.
                             String fichero,
                             long bytes,
                             // Momento del registro en el repositorio.
                             OffsetDateTime registrada,
                             // Si la BBDD sigue existiendo en el servidor (se puede haber borrado a mano).
                             // Null en los servidores de otros equipos: no se guarda su contraseña, no se comprueba.
                             Boolean existe,
                             // «host:puerto» del PostgreSQL de otro equipo; vacío = el servidor de la aplicación.
                             String servidor) implements Serializable {

    /** Tamaño del dump legible (KB, MB...). */
    public String tamano() {
        return Tamanos.legible(bytes);
    }

    /** Momento del registro en la zona horaria del equipo (PostgreSQL lo da en UTC). */
    public LocalDateTime registradaLocal() {
        return registrada.atZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime();
    }

    /** Dónde está la BBDD, para mostrarlo. */
    public String donde() {
        return servidor == null || servidor.isBlank() ? "Aplicación" : servidor;
    }
}
