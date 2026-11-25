package es.tfg.sqlanalyzer.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Quién ha creado cada BBDD del módulo 1 (paso 5), en la BBDD propia (H2). Sirve para que el rol USUARIO solo vea y
 * use las suyas. Las BBDD sin fila (creadas antes de existir esta tabla o fuera de la aplicación) solo las ven
 * ADMIN y ANALYST.
 */
@Entity
@Table(name = "bbdd_propietarios")
@Getter
@Setter
@NoArgsConstructor
public class BbddPropietario {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Nombre de la BBDD en PostgreSQL (único: no puede haber dos con el mismo nombre en el servidor).
    @Column(nullable = false, unique = true, length = 63)
    private String nombre;

    // Usuario de la aplicación que la ha creado.
    @Column(nullable = false, length = 50)
    private String username;

    // Constructor para crear un propietario de BBDD con nombre y usuario.
    public BbddPropietario(String nombre, String username) {
        this.nombre = nombre;
        this.username = username;
    }
}
