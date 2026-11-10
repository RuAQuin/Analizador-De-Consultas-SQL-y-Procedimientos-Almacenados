package es.tfg.sqlanalyzer.api;

import java.time.Duration;
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
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(3));
        factory.setReadTimeout(timeout);
        this.rest = builder.baseUrl(url).requestFactory(factory).build();
        this.url = url;
    }

    // Paso 1 del módulo 1: pide a la API que parsee el DDL con pglast.
    public ValidacionDdl validarDdl(String ddl) {
        return post("/bbdd/ddl", Map.of("ddl", ddl), ValidacionDdl.class);
    }

    // Paso 3 del módulo 1: envía el número de filas de cada tabla y recibe una muestra del prototipo.
    public PrototipoDatos definirPrototipo(String ddl, Map<String, Integer> filas) {
        return post("/bbdd/prototipo", Map.of("ddl", ddl, "filas", filas), PrototipoDatos.class);
    }

    // Envía una petición POST a la API Python y devuelve la respuesta parseada como tipo T.
    private <T> T post(String ruta, Object cuerpo, Class<T> tipo) {
        try {
            T respuesta = rest.post()
                    .uri(ruta)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(cuerpo)
                    .retrieve()
                    .body(tipo);
            if (respuesta == null) {
                throw new ApiNoDisponibleException("La API Python ha devuelto una respuesta vacía", null);
            }
            return respuesta;
        } catch (RestClientException e) {
            throw new ApiNoDisponibleException(
                    "No se ha podido contactar con la API Python (" + url + "). ¿Está arrancada?", e);
        }
    }
}
