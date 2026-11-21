package es.tfg.sqlanalyzer.api;

import java.io.OutputStream;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Cliente REST de la API Python. La WebApp nunca se conecta a las BBDD:
 * todo pasa por aquí.
 */
@Component
public class ApiPythonClient {

    private final RestClient rest;
    private final String url;

    // Constructor que inyecta el RestClient y la URL de la API Python desde application.properties.
    public ApiPythonClient(RestClient.Builder builder,
                           @Value("${app.api.url}") String url,
                           @Value("${app.api.timeout:30s}") Duration timeout) {
        var factory = new SimpleClientHttpRequestFactory(); // Crea un factory para configurar el tiempo de espera de las peticiones HTTP.
        factory.setConnectTimeout(Duration.ofSeconds(3)); // Tiempo de espera para establecer la conexión con la API Python.
        factory.setReadTimeout(timeout); // Tiempo de espera para recibir la respuesta de la API Python.
        this.rest = builder.baseUrl(url).requestFactory(factory).build(); // Crea un cliente REST con la URL base de la API Python y el tiempo de espera configurado.
        this.url = url; // Guarda la URL de la API Python para usarla en los mensajes de error.
    }

    // Paso 1 del módulo 1: pide a la API que parsee el DDL con pglast.
    public ValidacionDdl validarDdl(String ddl) {
        return post("/bbdd/ddl", Map.of("ddl", ddl), ValidacionDdl.class);
    }

    // Paso 3 del módulo 1: envía el número de filas de cada tabla y recibe una muestra del prototipo.
    public PrototipoDatos definirPrototipo(String ddl, Map<String, Integer> filas) {
        return post("/bbdd/prototipo", Map.of("ddl", ddl, "filas", filas), PrototipoDatos.class);
    }

    // Pasos 4 y 5 del módulo 1: tras la confirmación del usuario, crea la BBDD y sus tablas.
    public CreacionBbdd crearBbdd(String nombre, String ddl, Map<String, Integer> filas) {
        return post("/bbdd/crear", Map.of("nombre", nombre, "ddl", ddl, "filas", filas), CreacionBbdd.class);
    }

    // Paso 6 del módulo 1: inserta los datos del prototipo en la BBDD creada en el paso 5.
    public InsercionDatos insertarDatos(String nombre, String ddl, Map<String, Integer> filas) {
        return post("/bbdd/insertar", Map.of("nombre", nombre, "ddl", ddl, "filas", filas), InsercionDatos.class);
    }

    // Paso 7 del módulo 1: ANALYZE de las tablas para cerrar la carga.
    public AnalisisBbdd analizarBbdd(String nombre, String ddl, Map<String, Integer> filas) {
        return post("/bbdd/analizar", Map.of("nombre", nombre, "ddl", ddl, "filas", filas), AnalisisBbdd.class);
    }

    // Paso 8 del módulo 1: respaldo con pg_dump (formato custom) y registro como BBDD objetivo.
    public ExportacionBbdd exportarBbdd(String nombre, String ddl, Map<String, Integer> filas) {
        return post("/bbdd/exportar", Map.of("nombre", nombre, "ddl", ddl, "filas", filas), ExportacionBbdd.class);
    }

    // Paso 8.2: BBDD objetivo registradas, la última primero.
    public List<BbddRegistrada> listarRegistro() {
        // Llama a la API Python para obtener el registro de BBDD objetivo y lo devuelve como una lista de objetos BbddRegistrada.
        try {
            BbddRegistrada[] registradas = rest.get().uri("/bbdd/registro").retrieve().body(BbddRegistrada[].class);
            return registradas == null ? List.of() : List.of(registradas);
        // Si hay un error al contactar con la API Python, lanza una excepción personalizada con un mensaje de error.
        } catch (RestClientException e) {
            throw new ApiNoDisponibleException("No se ha podido leer el registro de BBDD de la API Python (" + url + ")", e);
        }
    }

    // Paso 8.1: copia el dump en la salida (sin cargarlo entero en memoria). False si no existe.
    public boolean descargarDump(String fichero, OutputStream salida) {
        try {
            // Envía una petición GET a la API Python para descargar el dump del fichero especificado.
            return Boolean.TRUE.equals(rest.get().uri("/bbdd/dumps/{fichero}", fichero).exchange((peticion, respuesta) -> {
                // Si la respuesta es 404, significa que el fichero no existe, por lo que devuelve false.
                if (respuesta.getStatusCode().value() == 404) {
                    return false;
                }
                // Si la respuesta no es 2xx, lanza una excepción indicando que la API Python no ha podido enviar el dump.
                if (!respuesta.getStatusCode().is2xxSuccessful()) {
                    throw new ApiNoDisponibleException("La API Python no ha podido enviar el dump", null);
                }
                // Si la respuesta es 2xx, transfiere el contenido del cuerpo de la respuesta al OutputStream proporcionado.
                respuesta.getBody().transferTo(salida);
                return true;
            }));
        // Si la respuesta es nula, lanza una excepción indicando que la API Python ha devuelto una respuesta vacía.
        } catch (RestClientException e) {
            throw new ApiNoDisponibleException(
                    "No se ha podido contactar con la API Python (" + url + "). ¿Está arrancada?", e);
        }
    }

    // Envía una petición POST a la API Python y devuelve la respuesta parseada como tipo T.
    private <T> T post(String ruta, Object cuerpo, Class<T> tipo) {
        try {
            // Envía la petición POST a la API Python con la ruta, el cuerpo y el tipo de respuesta esperado.
            T respuesta = rest.post()
                    .uri(ruta) // Construye la URI completa de la petición a partir de la ruta relativa.
                    .contentType(MediaType.APPLICATION_JSON) // Indica que el cuerpo de la petición es JSON.
                    .body(cuerpo) // Establece el cuerpo de la petición con el objeto proporcionado.
                    .retrieve() // Envía la petición y espera la respuesta.
                    .body(tipo); // Parsea la respuesta JSON a un objeto del tipo especificado.
            // Si la respuesta es nula --> error.
            if (respuesta == null) {
                throw new ApiNoDisponibleException("La API Python ha devuelto una respuesta vacía", null);
            }
            return respuesta;
        } catch (RestClientException e) {
            // Si hay un error al contactar con la API Python, lanza una excepción personalizada con un mensaje de error.
            throw new ApiNoDisponibleException(
                    "No se ha podido contactar con la API Python (" + url + "). ¿Está arrancada?", e);
        }
    }
}
