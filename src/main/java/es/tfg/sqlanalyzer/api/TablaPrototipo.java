package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/** Tabla del prototipo (paso 3): filas pedidas por el usuario y muestra de las primeras filas. */
public record TablaPrototipo(String tabla,
                             int filas,
                             List<ColumnaPrototipo> columnas,
                             List<List<String>> muestra) implements Serializable {
}
