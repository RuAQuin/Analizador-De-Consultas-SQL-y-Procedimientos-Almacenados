package es.tfg.sqlanalyzer.api;

import java.io.Serializable;

/** Tabla intermedia creada por la API para romper un ciclo de FK; sustituye a la FK indicada. */
public record TablaIntermedia(String tabla, ClaveForanea sustituye) implements Serializable {
}
