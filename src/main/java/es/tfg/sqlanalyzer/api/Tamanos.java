package es.tfg.sqlanalyzer.api;

import java.util.Locale;

/** Tamaños de fichero legibles: 950 B, 12.4 KB, 3.1 MB... */
final class Tamanos {

    private static final String[] UNIDADES = {"B", "KB", "MB", "GB"};

    private Tamanos() {
    }

    // Convierte un tamaño en bytes a un tamaño legible (KB, MB...).
    static String legible(long bytes) {
        double valor = bytes;
        int unidad = 0;
        while (valor >= 1024 && unidad < UNIDADES.length - 1) {
            valor /= 1024;
            unidad++;
        }
        return unidad == 0 ? bytes + " B" : String.format(Locale.ROOT, "%.1f %s", valor, UNIDADES[unidad]);
    }
}
