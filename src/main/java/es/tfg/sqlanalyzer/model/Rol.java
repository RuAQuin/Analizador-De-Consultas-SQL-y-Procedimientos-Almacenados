package es.tfg.sqlanalyzer.model;

/**
 * Roles de acceso a la aplicación.
 *  - ADMIN   : todos los permisos (todas las BBDD, paso 9, logs y gestión de usuarios).
 *  - ANALYST : todas las BBDD y los logs, pero no el paso 9 (restaurar en otro servidor) ni la gestión de usuarios.
 *  - USUARIO : solo las BBDD que ha creado él (ver {@link BbddPropietario}) y los logs; sin paso 9 ni gestión de usuarios.
 */
public enum Rol {
    ADMIN,
    ANALYST,
    USUARIO
}
