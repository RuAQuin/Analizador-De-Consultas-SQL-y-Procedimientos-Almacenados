package es.tfg.sqlanalyzer.api;

import java.io.Serializable;
import java.util.List;

/** Árbol de agrupación (paso 2.2). Los nodos van en preorden: cada tabla antes que las que cuelgan de ella. */
public record Arbol(String raiz, List<NodoArbol> nodos) implements Serializable {
}
