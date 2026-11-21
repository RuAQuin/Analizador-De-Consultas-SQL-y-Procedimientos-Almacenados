package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.api.AnalisisBbdd;
import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.CreacionBbdd;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.ExportacionBbdd;
import es.tfg.sqlanalyzer.api.InsercionDatos;
import es.tfg.sqlanalyzer.api.PrototipoDatos;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import es.tfg.sqlanalyzer.form.CreacionBbddForm;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Módulo 1: generación de BBDD.
 * El estado del módulo (DDL validado, filas, prototipo, BBDD creada, datos insertados, ANALYZE y exportación) se guarda en la sesión para
 * poder avanzar paso a paso: la API Python no guarda nada entre peticiones.
 */
@Controller
@RequestMapping("/bbdd")
public class BbddController {

    static final String SESION_FORM = "bbdd.form";
    static final String SESION_VALIDACION = "bbdd.validacion";
    static final String SESION_FILAS = "bbdd.filas";
    static final String SESION_PROTOTIPO = "bbdd.prototipo";
    static final String SESION_CREACION = "bbdd.creacion";
    static final String SESION_INSERCION = "bbdd.insercion";
    static final String SESION_ANALISIS = "bbdd.analisis";
    static final String SESION_EXPORTACION = "bbdd.exportacion";
    // Nombre de los dumps: <bbdd>_<AAAAMMDD>_<HHMMSS>.dump (o .sql, de exportaciones anteriores), como en la API.
    static final Pattern FICHERO_DUMP = Pattern.compile("^[a-z_][a-z0-9_]{0,62}_\\d{8}_\\d{6}\\.(dump|sql)$");
    // Filas que se proponen por defecto para cada tabla.
    static final int FILAS_POR_DEFECTO = 10;

    private final ApiPythonClient api;

    public BbddController(ApiPythonClient api) {
        this.api = api;
    }

    @ModelAttribute("activePage")
    // Atributo de modelo que indica la página activa en la navegación.
    public String activePage() {
        return "bbdd";
    }

    @GetMapping
    // Muestra la pantalla con lo que haya en la sesión: el DDL validado (pasos 1 y 2) y el prototipo (paso 3).
    public String formulario(Model model, HttpSession sesion) {
        if (!model.containsAttribute("form")) {
            Object form = sesion.getAttribute(SESION_FORM);
            model.addAttribute("form", form != null ? form : new CreacionBbddForm());
        }
        rellenarModelo(model, sesion);
        return "bbdd";
    }

    @PostMapping
    // Paso 1: la API parsea el DDL con pglast. Paso 2: lee las FK, forma los árboles y los ordena con Kahn.
    // Si algo falla (sintaxis, FK a una tabla inexistente, ciclo entre tablas o entre árboles...), se vuelve al formulario
    // con el DDL escrito y los errores, para que el usuario lo corrija.
    public String validarDdl(@Valid @ModelAttribute("form") CreacionBbddForm form,
                             BindingResult result,
                             Model model,
                             HttpSession sesion,
                             RedirectAttributes ra /* Se utiliza para pasar atributos entre redirecciones */) {
        // Un DDL nuevo invalida lo anterior: el prototipo y la BBDD creada dependían del DDL.
        limpiarSesion(sesion);
        if (result.hasErrors()) {
            return "bbdd";
        }

        // Paso 1 y 2: parseo, ordenación y árboles de agrupación.
        ValidacionDdl validacion;
        try {
            validacion = api.validarDdl(form.getDefinicionTablas());
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
            return "bbdd";
        }

        // Si hay errores de sintaxis, FK a tabla inexistente, ciclo entre tablas o entre árboles --> Error
        if (!validacion.valido()) {
            for (ErrorDdl error : validacion.errores()) {
                result.rejectValue("definicionTablas", "ddl.invalido", error.descripcion());
            }
            return "bbdd";
        }

        // Guardamos en la sesión el DDL validado y la validación (orden de tablas, árboles de agrupación y orden de carga).
        sesion.setAttribute(SESION_FORM, form);
        sesion.setAttribute(SESION_VALIDACION, validacion);
        ra.addFlashAttribute("aviso", "El DDL es correcto: pglast lo ha parseado, las tablas se han ordenado con Kahn,"
                + " se han formado los árboles de agrupación y se ha decidido su orden de carga."
                + " Ahora indica cuántas filas quieres en cada tabla.");
        return "redirect:/bbdd";
    }

    @PostMapping("/prototipo")
    // Paso 3: el usuario indica el número de filas de cada tabla (campos filas[tabla]).
    // Si hay avisos de coherencia, se vuelve a la pantalla con las filas escritas para corregirlas.
    public String definirPrototipo(@RequestParam Map<String, String> parametros,
                                   Model model,
                                   HttpSession sesion,
                                   RedirectAttributes ra) {
        // Comprobamos que haya un DDL validado y que no se haya creado ya la BBDD.
        CreacionBbddForm form = (CreacionBbddForm) sesion.getAttribute(SESION_FORM);
        ValidacionDdl validacion = (ValidacionDdl) sesion.getAttribute(SESION_VALIDACION);
        if (form == null || validacion == null) {
            ra.addFlashAttribute("error", "Primero valida el DDL de las tablas.");
            return "redirect:/bbdd";
        }
        if (yaCreada(sesion, ra)) {
            return "redirect:/bbdd";
        }

        // Filas escritas por el usuario, en el orden de las tablas (se conservan aunque haya errores).
        Map<String, String> escritas = new LinkedHashMap<>();
        for (TablaOrdenada t : validacion.orden()) {
            escritas.put(t.tabla(), parametros.getOrDefault("filas[" + t.tabla() + "]", "").trim());
        }
        sesion.removeAttribute(SESION_PROTOTIPO);

        // Convertimos las filas escritas en números; si alguna no lo es, añadimos el error.
        List<String> errores = new ArrayList<>();
        Map<String, Integer> filas = numeros(escritas, errores);

        // Paso 3: la API genera el prototipo de datos y comprueba la coherencia de los números de filas.
        PrototipoDatos prototipo = null;
        if (errores.isEmpty()) {
            try {
                prototipo = api.definirPrototipo(form.getDefinicionTablas(), filas);
                prototipo.errores().forEach(e -> errores.add(e.descripcion()));
            } catch (ApiNoDisponibleException e) {
                model.addAttribute("error", e.getMessage());
            }
        }

        // Si hay errores de coherencia, se vuelve a la pantalla con las filas escritas para corregirlas.
        if (prototipo == null || !prototipo.valido()) {
            model.addAttribute("form", form);
            model.addAttribute("erroresPrototipo", errores);
            rellenarModelo(model, sesion);
            model.addAttribute("filas", escritas);
            return "bbdd";
        }

        // Guardamos en la sesión las filas y el prototipo de datos.
        sesion.setAttribute(SESION_FILAS, escritas);
        sesion.setAttribute(SESION_PROTOTIPO, prototipo);
        ra.addFlashAttribute("aviso", "El prototipo es correcto. Revisa la vista previa de cada tabla.");
        return "redirect:/bbdd#prototipo";
    }

    @PostMapping("/crear")
    // Paso 4: el usuario confirma con el botón "Confirmar y crear la BBDD"; la API revisa el nombre contra el servidor
    // (formato, BBDD reservada o que ya existe). Paso 5: CREATE DATABASE y CREATE TABLE en el orden de Kahn.
    // Si algo falla, la API no deja nada creado y se muestra el aviso.
    public String crearBbdd(Model model, HttpSession sesion, RedirectAttributes ra) {
        // El formulario y las filas se guardan en la sesión para poder volver a la pantalla si hay errores.
        CreacionBbddForm form = (CreacionBbddForm) sesion.getAttribute(SESION_FORM);
        @SuppressWarnings("unchecked")
        Map<String, String> filas = (Map<String, String>) sesion.getAttribute(SESION_FILAS);

        // Comprobamos que haya un DDL validado.
        if (form == null || sesion.getAttribute(SESION_VALIDACION) == null) {
            ra.addFlashAttribute("error", "Primero valida el DDL de las tablas.");
            return "redirect:/bbdd";
        }

        // Comprobamos que haya un prototipo.
        if (filas == null || sesion.getAttribute(SESION_PROTOTIPO) == null) {
            ra.addFlashAttribute("error", "Primero genera la vista previa del prototipo de datos.");
            return "redirect:/bbdd";
        }

        // Comprobamos que no se haya creado ya la BBDD.
        if (yaCreada(sesion, ra)) {
            return "redirect:/bbdd";
        }

        // Paso 4 y 5: la API crea la BBDD y sus tablas en el orden de Kahn; si algo falla, no deja nada creado.
        List<String> errores = new ArrayList<>();
        CreacionBbdd creacion = null;
        try {
            creacion = api.crearBbdd(form.getNombreBbdd(), form.getDefinicionTablas(), numeros(filas, errores));
            creacion.errores().forEach(e -> errores.add(e.descripcion()));
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
        }

        // Si hay errores de coherencia, se vuelve a la pantalla con las filas escritas para corregirlas.
        if (creacion == null || !creacion.valido()) {
            model.addAttribute("form", form);
            model.addAttribute("erroresCreacion", errores);
            rellenarModelo(model, sesion);
            return "bbdd";
        }

        // Guardamos en la sesión la BBDD creada y mostramos el aviso.
        sesion.setAttribute(SESION_CREACION, creacion);
        ra.addFlashAttribute("aviso", "Se ha creado la base de datos «" + creacion.bbdd() + "» con "
                + creacion.tablas().size() + " tablas, en el orden de Kahn.");
        return "redirect:/bbdd#creacion";
    }

    @PostMapping("/insertar")
    // Paso 6: la API genera las tuplas siguiendo el diagrama (árbol a árbol y en profundidad) y las escribe
    // tabla a tabla en el orden de Kahn en la BBDD creada en el paso 5. Si una fila falla, no se inserta nada.
    public String insertarDatos(Model model, HttpSession sesion, RedirectAttributes ra) {
        CreacionBbddForm form = (CreacionBbddForm) sesion.getAttribute(SESION_FORM);
        @SuppressWarnings("unchecked")
        Map<String, String> filas = (Map<String, String>) sesion.getAttribute(SESION_FILAS);

        // Comprobamos que la BBDD esté creada (paso 5) y que no se hayan insertado ya los datos.
        if (form == null || filas == null || sesion.getAttribute(SESION_CREACION) == null) {
            ra.addFlashAttribute("error", "Primero crea la base de datos.");
            return "redirect:/bbdd";
        }
        // Comprobamos que no se hayan insertado ya los datos.
        InsercionDatos anterior = (InsercionDatos) sesion.getAttribute(SESION_INSERCION);
        if (anterior != null) {
            ra.addFlashAttribute("error", "Los datos de «" + anterior.bbdd() + "» ya están insertados."
                    + " Para empezar otra, valida un DDL nuevo.");
            return "redirect:/bbdd";
        }

        List<String> errores = new ArrayList<>();
        InsercionDatos insercion = null;
        // Paso 6: la API genera las tuplas y las inserta en la BBDD creada en el paso 5; si algo falla, no deja nada insertado.
        try {
            insercion = api.insertarDatos(form.getNombreBbdd(), form.getDefinicionTablas(), numeros(filas, errores));
            insercion.errores().forEach(e -> errores.add(e.descripcion()));
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
        }

        // Si algo falla (por ejemplo, una fila que incumple un CHECK), se muestra el aviso y se puede reintentar.
        if (insercion == null || !insercion.valido()) {
            model.addAttribute("form", form);
            model.addAttribute("erroresInsercion", errores);
            rellenarModelo(model, sesion);
            return "bbdd";
        }

        // Guardamos en la sesión los datos insertados y mostramos el aviso.
        sesion.setAttribute(SESION_INSERCION, insercion);
        ra.addFlashAttribute("aviso", "Se han insertado " + insercion.totalFilas() + " filas en «" + insercion.bbdd()
                + "» (" + insercion.segundos() + " s).");
        return "redirect:/bbdd#insercion";
    }

    @PostMapping("/analizar")
    // Paso 7: ANALYZE para cerrar la carga. La API analiza cada tabla en el orden de Kahn para que el planificador
    // tenga estadísticas reales de los datos insertados en el paso 6.
    public String analizarBbdd(Model model, HttpSession sesion, RedirectAttributes ra) {
        CreacionBbddForm form = (CreacionBbddForm) sesion.getAttribute(SESION_FORM);
        @SuppressWarnings("unchecked")
        Map<String, String> filas = (Map<String, String>) sesion.getAttribute(SESION_FILAS);

        // Comprobamos que los datos estén insertados (paso 6).
        if (form == null || filas == null || sesion.getAttribute(SESION_INSERCION) == null) {
            ra.addFlashAttribute("error", "Primero inserta los datos.");
            return "redirect:/bbdd";
        }
        // Comprobamos que no se haya hecho ya el ANALYZE (Resultados del anterior ANALYZE = resultados del nuevo ANALYZE).
        AnalisisBbdd anterior = (AnalisisBbdd) sesion.getAttribute(SESION_ANALISIS);
        if (anterior != null) {
            ra.addFlashAttribute("error", "Las tablas de «" + anterior.bbdd() + "» ya están analizadas."
                    + " Para empezar otra, valida un DDL nuevo.");
            return "redirect:/bbdd";
        }

        List<String> errores = new ArrayList<>();
        AnalisisBbdd analisis = null;
        try {
            analisis = api.analizarBbdd(form.getNombreBbdd(), form.getDefinicionTablas(), numeros(filas, errores));
            analisis.errores().forEach(e -> errores.add(e.descripcion()));
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
        }

        // Si algo falla (por ejemplo, se ha perdido la conexión), se muestra el aviso y se puede reintentar.
        if (analisis == null || !analisis.valido()) {
            model.addAttribute("form", form);
            model.addAttribute("erroresAnalisis", errores);
            rellenarModelo(model, sesion);
            return "bbdd";
        }

        // Guardamos en la sesión el resultado del ANALYZE y mostramos el aviso.
        sesion.setAttribute(SESION_ANALISIS, analisis);
        ra.addFlashAttribute("aviso", "Se han analizado las " + analisis.tablas().size() + " tablas de «"
                + analisis.bbdd() + "» (" + analisis.segundos() + " s): el planificador ya tiene estadísticas reales.");
        return "redirect:/bbdd#analisis";
    }

    @PostMapping("/exportar")
    // Paso 8: el servidor respalda la BBDD con COPY ... TO PROGRAM 'pg_dump -F c' (8.1) y la API la registra como BBDD objetivo
    // en el repositorio (8.2). La carga debe estar cerrada con el ANALYZE (paso 7).
    public String exportarBbdd(Model model, HttpSession sesion, RedirectAttributes ra) {
        CreacionBbddForm form = (CreacionBbddForm) sesion.getAttribute(SESION_FORM);
        @SuppressWarnings("unchecked")
        Map<String, String> filas = (Map<String, String>) sesion.getAttribute(SESION_FILAS);

        // Comprobamos que la carga esté cerrada (paso 7).
        if (form == null || filas == null || sesion.getAttribute(SESION_ANALISIS) == null) {
            ra.addFlashAttribute("error", "Primero ejecuta el ANALYZE.");
            return "redirect:/bbdd";
        }
        // Comprobamos que no se haya exportado ya.
        ExportacionBbdd anterior = (ExportacionBbdd) sesion.getAttribute(SESION_EXPORTACION);
        if (anterior != null) {
            ra.addFlashAttribute("error", "«" + anterior.bbdd() + "» ya está exportada y registrada."
                    + " Para empezar otra, valida un DDL nuevo.");
            return "redirect:/bbdd";
        }

        List<String> errores = new ArrayList<>();
        ExportacionBbdd exportacion = null;
        // La API respalda la BBDD y la registra como BBDD objetivo; si algo falla, no deja nada registrado.
        try {
            exportacion = api.exportarBbdd(form.getNombreBbdd(), form.getDefinicionTablas(), numeros(filas, errores));
            exportacion.errores().forEach(e -> errores.add(e.descripcion()));
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
        }

        // Si algo falla (pg_dump, repositorio...), se muestra el aviso y se puede reintentar.
        if (exportacion == null || !exportacion.valido()) {
            model.addAttribute("form", form);
            model.addAttribute("erroresExportacion", errores);
            rellenarModelo(model, sesion);
            return "bbdd";
        }

        // Guardamos en la sesión la exportación y mostramos el aviso.
        sesion.setAttribute(SESION_EXPORTACION, exportacion);
        ra.addFlashAttribute("aviso", "Se ha exportado «" + exportacion.bbdd() + "» en " + exportacion.fichero()
                + " (" + exportacion.tamano() + ") y se ha registrado como BBDD objetivo.");
        return "redirect:/bbdd#exportacion";
    }

    @GetMapping("/dumps/{fichero}")
    // Paso 8.1: descarga del dump. La WebApp no lee el fichero: se lo pide a la API y lo copia en la respuesta.
    public void descargarDump(@PathVariable String fichero, HttpServletResponse respuesta) throws IOException {
        // Comprobamos que el nombre del fichero sea válido (como en la API). Si no, 404.
        if (!FICHERO_DUMP.matcher(fichero).matches()) {
            respuesta.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        // El tipo de contenido depende de la extensión del fichero: .sql o .dump (binario).
        respuesta.setContentType(fichero.endsWith(".sql") ? "application/sql" : "application/octet-stream");
        // El nombre del fichero se envía en el encabezado Content-Disposition para que el navegador lo descargue.
        respuesta.setHeader(HttpHeaders.CONTENT_DISPOSITION,
                ContentDisposition.attachment().filename(fichero).build().toString());
        try {
            // La API descarga el dump y lo escribe en la respuesta. Si no existe, 404.
            if (!api.descargarDump(fichero, respuesta.getOutputStream())) {
                respuesta.reset();
                respuesta.sendError(HttpServletResponse.SC_NOT_FOUND, "No existe el dump «" + fichero + "»");
            }
        } catch (ApiNoDisponibleException e) {
            if (!respuesta.isCommitted()) {
                respuesta.reset();
                respuesta.sendError(HttpServletResponse.SC_SERVICE_UNAVAILABLE, e.getMessage());
            }
        }
    }

    // Convierte las filas escritas en números; si alguna no lo es, añade el error.
    private static Map<String, Integer> numeros(Map<String, String> escritas, List<String> errores) {
        Map<String, Integer> filas = new LinkedHashMap<>();
        escritas.forEach((tabla, texto) -> {
            try {
                filas.put(tabla, Integer.parseInt(texto));
            } catch (NumberFormatException e) {
                errores.add("El número de filas de «" + tabla + "» debe ser un número entero");
            }
        });
        return filas;
    }

    // Una vez creada la BBDD sus tablas ya existen: para cambiar algo hay que validar otro DDL.
    private static boolean yaCreada(HttpSession sesion, RedirectAttributes ra) {
        CreacionBbdd creacion = (CreacionBbdd) sesion.getAttribute(SESION_CREACION);
        if (creacion == null) {
            return false;
        }
        ra.addFlashAttribute("error", "La base de datos «" + creacion.bbdd() + "» ya está creada."
                + " Para empezar otra, valida un DDL nuevo.");
        return true;
    }

    // Añade al modelo lo guardado en la sesión. Las filas solo si no vienen ya en el modelo
    // (tras un aviso de coherencia se muestran las que escribió el usuario).
    private void rellenarModelo(Model model, HttpSession sesion) {
        ValidacionDdl validacion = (ValidacionDdl) sesion.getAttribute(SESION_VALIDACION);
        if (validacion == null) {
            return;
        }
        // Pasos 2.1, 2.2 y 2.3.
        model.addAttribute("orden", validacion.orden());
        model.addAttribute("clavesForaneas", validacion.clavesForaneas());
        model.addAttribute("arboles", validacion.arboles());
        model.addAttribute("ordenCarga", validacion.ordenCarga());
        // Paso 3.
        if (!model.containsAttribute("filas")) {
            @SuppressWarnings("unchecked")
            Map<String, String> filas = (Map<String, String>) sesion.getAttribute(SESION_FILAS);
            if (filas == null) {
                filas = new LinkedHashMap<>();
                for (TablaOrdenada t : validacion.orden()) {
                    filas.put(t.tabla(), String.valueOf(FILAS_POR_DEFECTO));
                }
            }
            model.addAttribute("filas", filas);
        }
        model.addAttribute("prototipo", sesion.getAttribute(SESION_PROTOTIPO));
        // Pasos 4 y 5.
        model.addAttribute("creacion", sesion.getAttribute(SESION_CREACION));
        // Paso 6.
        model.addAttribute("insercion", sesion.getAttribute(SESION_INSERCION));
        // Paso 7.
        model.addAttribute("analisis", sesion.getAttribute(SESION_ANALISIS));
        // Paso 8: tras exportar, se muestran también las BBDD objetivo registradas.
        Object exportacion = sesion.getAttribute(SESION_EXPORTACION);
        model.addAttribute("exportacion", exportacion);
        if (exportacion != null) {
            try {
                model.addAttribute("registro", api.listarRegistro());
            } catch (ApiNoDisponibleException e) {
                model.addAttribute("registro", List.of());
            }
        }
    }

    private void limpiarSesion(HttpSession sesion) {
        sesion.removeAttribute(SESION_FORM);
        sesion.removeAttribute(SESION_VALIDACION);
        sesion.removeAttribute(SESION_FILAS);
        sesion.removeAttribute(SESION_PROTOTIPO);
        sesion.removeAttribute(SESION_CREACION);
        sesion.removeAttribute(SESION_INSERCION);
        sesion.removeAttribute(SESION_ANALISIS);
        sesion.removeAttribute(SESION_EXPORTACION);
    }
}
