# Analizador de Consultas SQL y Procedimientos Almacenados.
El proyecto consiste en una interfaz WebApp realizada con spring-boot que se conecta a una base de datos PostgreSQL a través de una API programada con Python. El proyecto se divide en tres objetivos principales:
  1. Crear scripts de creación de BBDD con Python. El script debe de:
     
    a. Generar BBDD.
    
    b. Insertar datos en las tablas conforme a la petición del usuario.
    
    c. Exportar el script completo.
  2. Realizar análisis de consultas y procedimientos. Se debe:
     
    a.Analizar estáticamente las consultas y procedimientos con pglast y detectar sus malas prácticas.
    
    b. Analizar su ejecución con los Explain Plans.
    
    c. Dar formato SQL con pglast para mostrarse en la WebApp.
    
    d. Mostrar recomendaciones para para optimizar los resultados.
  3. Leer los logs generados con JPA e Hibernate. Se seguirán los siguientes pasos:
     
    a. Cargar el .txt con los logs generados.
    
    b. Buscar las consultas en los logs.
    
    c. Analizar las consultas de los logs y almacenar los resultados de los análisis.

TFG: Grado en Ingeniería Informática - Universidad de Burgos.

Alumno: Rubén Alonso Quintana.

