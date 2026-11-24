package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.api.ClaveForanea;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** Paso 3: filas propuestas por defecto (nivel 0 con FILAS_POR_DEFECTO, hijas con el producto de sus padres). */
class FilasPorDefectoTests {

    private static ClaveForanea fk(String tabla, String padre) {
        return new ClaveForanea(tabla, List.of(padre + "_id"), padre, List.of());
    }

    private static ValidacionDdl validacion(List<ClaveForanea> fks, List<TablaOrdenada> orden) {
        return new ValidacionDdl(true, List.of(), List.of(), fks, orden, List.of(), List.of());
    }

    @Test
    void nivelCeroConFilasPorDefectoYHijasConElProductoDeSusPadres() {
        // clientes y productos (nivel 0) → pedidos (1 padre) → lineas (2 padres); empleados se apunta a sí misma.
        Map<String, String> filas = BbddController.filasPorDefecto(validacion(
                List.of(fk("pedidos", "clientes"), fk("lineas", "pedidos"), fk("lineas", "productos"),
                        fk("empleados", "empleados")),
                List.of(new TablaOrdenada("clientes", 0), new TablaOrdenada("productos", 0),
                        new TablaOrdenada("empleados", 0), new TablaOrdenada("pedidos", 1),
                        new TablaOrdenada("lineas", 2))));

        // Mismo orden de Kahn que en la pantalla.
        assertEquals(List.of("clientes", "productos", "empleados", "pedidos", "lineas"), List.copyOf(filas.keySet()));
        assertEquals(Map.of("clientes", "10", "productos", "10", "empleados", "10", "pedidos", "10", "lineas", "100"),
                filas);
    }

    @Test
    void dosFkAlMismoPadreCuentanDosVecesYElProductoSeLimitaAlMaximo() {
        // vuelos: origen y destino → aeropuertos (10 x 10); billetes: vuelos x pasajeros x asientos.
        Map<String, String> filas = BbddController.filasPorDefecto(validacion(
                List.of(fk("vuelos", "aeropuertos"), fk("vuelos", "aeropuertos"),
                        fk("billetes", "vuelos"), fk("billetes", "pasajeros"), fk("billetes", "asientos"),
                        fk("revisiones", "billetes"), fk("revisiones", "vuelos")),
                List.of(new TablaOrdenada("aeropuertos", 0), new TablaOrdenada("pasajeros", 0),
                        new TablaOrdenada("asientos", 0), new TablaOrdenada("vuelos", 1),
                        new TablaOrdenada("billetes", 2), new TablaOrdenada("revisiones", 3))));

        assertEquals("100", filas.get("vuelos"));
        assertEquals("10000", filas.get("billetes"));
        // 10.000 x 100 = 1.000.000 → se queda en el máximo que acepta la API.
        assertEquals(String.valueOf(BbddController.MAX_FILAS), filas.get("revisiones"));
    }
}
