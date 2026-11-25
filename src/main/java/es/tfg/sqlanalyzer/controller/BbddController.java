package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.api.AnalisisBbdd;
import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.BbddRegistrada;
import es.tfg.sqlanalyzer.api.CreacionBbdd;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.ExportacionBbdd;
import es.tfg.sqlanalyzer.api.InsercionDatos;
import es.tfg.sqlanalyzer.api.ProgresoInsercion;
import es.tfg.sqlanalyzer.api.PrototipoDatos;
import es.tfg.sqlanalyzer.api.PruebaServidor;
import es.tfg.sqlanalyzer.api.RestauracionBbdd;
import es.tfg.sqlanalyzer.api.Servidor;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import es.tfg.sqlanalyzer.form.CreacionBbddForm;
import es.tfg.sqlanalyzer.form.ServidorForm;
import es.tfg.sqlanalyzer.service.PermisosBbdd;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
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
    // Paso 9: última restauración en otro servidor y último servidor usado (con su contraseña, solo en la sesión).
    static final String SESION_RESTAURACION = "bbdd.restauracion";
    static final String SESION_SERVIDOR = "bbdd.servidor";
    // Nombre de los dumps: <bbdd>_<AAAAMMDD>_<HHMMSS>.dump (o .sql, de exportaciones anteriores), como en la API.
    static final Pattern FICHERO_DUMP = Pattern.compile("^[a-z_][a-z0-9_]{0,62}_\\d{8}_\\d{6}\\.(dump|sql)$");
    // Filas que se proponen por defecto para las tablas de nivel 0 (las hijas, ver filasPorDefecto).
    static final int FILAS_POR_DEFECTO = 10;
    // Máximo de filas por tabla que acepta la API (MAX_FILAS en prototipo.py).
    static final int MAX_FILAS = 100_000;

    private final ApiPythonClient api;
    // Qué BBDD puede ver y usar el usuario conectado (USUARIO: solo las suyas).
    private final PermisosBbdd permisos;

    public BbddController(ApiPythonClient api, PermisosBbdd permisos) {
        this.api = api;
        this.permisos = permisos;
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

    @PostMapping("/servidor/probar")
    // Paso 9: «Probar conexión» con el PostgreSQL de otro equipo. Solo recuerda el servidor probado (con su contraseña,
    // únicamente en la sesión) para no tener que volver a escribirla al restaurar.
    public String probarServidor(@Valid @ModelAttribute("servidorForm") ServidorForm servidorForm,
                                 BindingResult result,
                                 Model model,
                                 HttpSession sesion) {
        // Si la contraseña no se ha escrito, se usa la del último servidor usado (probado o restaurado) con el mismo host, puerto y usuario.
        completarContrasena(servidorForm, sesion);
        if (!result.hasErrors()) {
            // Si no hay errores de validación, se prueba la conexión con el servidor PostgreSQL especificado por el formulario.
            Servidor servidor = servidorForm.servidor();
            try {
                //La API prueba la conexión con el servidor PostgreSQL especificado por "servidor".
                PruebaServidor prueba = api.probarServidor(servidor);
                // Si la conexión es válida, se guarda el servidor en la sesión y se muestra un aviso de éxito.
                if (prueba.valido()) {
                    sesion.setAttribute(SESION_SERVIDOR, servidor);
                    model.addAttribute("aviso", "Conexión correcta con " + prueba.servidor() + " (PostgreSQL "
                            + prueba.version() + "): el usuario «" + servidor.usuario() + "» puede crear bases de datos.");
                // Si la conexión no es válida, se muestran los errores devueltos por la API.
                } else {
                    model.addAttribute("erroresRestauracion", prueba.errores().stream().map(ErrorDdl::descripcion).toList());
                }
            } catch (ApiNoDisponibleException e) {
                model.addAttribute("error", e.getMessage());
            }
        }
        // Se vuelve a la pantalla con el formulario del paso 1 y los errores de validación (si los hay).
        return pantalla(model, sesion);
    }

    @PostMapping("/restaurar")
    // Paso 9 (opcional): la API restaura el respaldo del paso 8 en el PostgreSQL de otro equipo con pg_restore --create,
    // ejecuta ANALYZE allí y registra la copia como BBDD objetivo de ese servidor. Se puede repetir en otros servidores.
    public String restaurar(@Valid @ModelAttribute("servidorForm") ServidorForm servidorForm,
                            BindingResult result,
                            Model model,
                            HttpSession sesion,
                            RedirectAttributes ra) {
        // Comprobamos que haya un respaldo del paso 8 en la sesión.
        ExportacionBbdd exportacion = (ExportacionBbdd) sesion.getAttribute(SESION_EXPORTACION);
        if (exportacion == null) {
            ra.addFlashAttribute("error", "Primero exporta la base de datos (paso 8).");
            return "redirect:/bbdd";
        }
        // Si la contraseña no se ha escrito, se usa la del último servidor usado (probado o restaurado) con el mismo host, puerto y usuario.
        completarContrasena(servidorForm, sesion);
        if (result.hasErrors()) {
            return pantalla(model, sesion);
        }

        Servidor servidor = servidorForm.servidor();
        RestauracionBbdd restauracion;
        try {
            // La API restaura el respaldo del paso 8 en el PostgreSQL de otro equipo, ejecuta ANALYZE allí y registra la copia como BBDD objetivo.
            restauracion = api.restaurarBbdd(exportacion.bbdd(), exportacion.fichero(), servidor);
        // Si hay un error al contactar con la API Python, se muestra el mensaje de error en la pantalla.
        } catch (ApiNoDisponibleException e) {
            model.addAttribute("error", e.getMessage());
            return pantalla(model, sesion);
        }
        // Si algo falla (no responde, ya existe, versión antigua...), se muestra el motivo y se puede reintentar.
        if (!restauracion.valido()) {
            model.addAttribute("erroresRestauracion", restauracion.errores().stream().map(ErrorDdl::descripcion).toList());
            return pantalla(model, sesion);
        }
        // Si la restauración es correcta, se guarda el servidor y la restauración en la sesión y se muestra un aviso de éxito.
        sesion.setAttribute(SESION_SERVIDOR, servidor);
        sesion.setAttribute(SESION_RESTAURACION, restauracion);
        ra.addFlashAttribute("aviso", "Se ha restaurado «" + restauracion.bbdd() + "» en " + restauracion.servidor()
                + " (PostgreSQL " + restauracion.version() + "): " + restauracion.tablas().size() + " tablas y "
                + restauracion.totalFilas() + " filas, ya analizadas (" + restauracion.segundos() + " s).");
        return "redirect:/bbdd#restauracion";
    }

    // Vuelve a la pantalla (sin redirigir) con el formulario del paso 1 de la sesión.
    private String pantalla(Model model, HttpSession sesion) {
        Object form = sesion.getAttribute(SESION_FORM);
        model.addAttribute("form", form != null ? form : new CreacionBbddForm());
        rellenarModelo(model, sesion);
        return "bbdd";
    }

    // La contraseña no se vuelve a mostrar: si viene vacía, se usa la del último servidor usado (probado o restaurado)
    // con el mismo host, puerto y usuario.
    private void completarContrasena(ServidorForm servidorForm, HttpSession sesion) {
        if (servidorForm.getContrasena() != null && !servidorForm.getContrasena().isEmpty()) {
            return;
        }
        Servidor conocido = (Servidor) sesion.getAttribute(SESION_SERVIDOR);
        if (conocido != null && servidorForm.getHost() != null && servidorForm.getUsuario() != null
                && conocido.host().equals(servidorForm.getHost().strip())
                && Integer.valueOf(conocido.puerto()).equals(servidorForm.getPuerto())
                && conocido.usuario().equals(servidorForm.getUsuario().strip())) {
            servidorForm.setContrasena(conocido.contrasena());
        }
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

        // Guardamos en la sesión la BBDD creada, apuntamos que es del usuario conectado y mostramos el aviso.
        sesion.setAttribute(SESION_CREACION, creacion);
        permisos.registrarPropietario(creacion.bbdd());
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

    @GetMapping("/insertar/progreso")
    @ResponseBody
    // Paso 6: reloj de la carga. Mientras dura POST /bbdd/insertar, carga.js pregunta cada segundo cómo va.
    // 204 si no hay ninguna inserción en marcha (aún no ha empezado o ya ha terminado) o no hay BBDD en la sesión.
    public ResponseEntity<ProgresoInsercion> progresoInsercion(HttpSession sesion) {
        // Comprobamos que haya un DDL validado y que se haya creado la BBDD (paso 5).
        CreacionBbddForm form = (CreacionBbddForm) sesion.getAttribute(SESION_FORM);
        // Si no hay BBDD en la sesión o no es del usuario (USUARIO con el nombre de una BBDD ajena), devolvemos 204 No Content.
        if (form == null || !permisos.puedeUsar(form.getNombreBbdd())) {
            return ResponseEntity.noContent().build();
        }
        try {
            // Preguntamos a la API Python cómo va la inserción de datos en la BBDD especificada por "nombreBbdd" (paso 6).
            ProgresoInsercion progreso = api.progresoInsercion(form.getNombreBbdd());
            return progreso == null ? ResponseEntity.noContent().build() : ResponseEntity.ok(progreso);
        // Si hay un error al contactar con la API Python, devolvemos 503 Service Unavailable.
        } catch (ApiNoDisponibleException e) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
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
        // Comprobamos que el nombre del fichero sea válido (como en la API) y que su BBDD sea del usuario
        // (USUARIO: solo las suyas). Si no, 404, sin decir si existe.
        if (!FICHERO_DUMP.matcher(fichero).matches() || !permisos.puedeUsar(bbddDelDump(fichero))) {
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

    // BBDD de un dump: el nombre del fichero sin «_<AAAAMMDD>_<HHMMSS>.dump» (ver FICHERO_DUMP).
    static String bbddDelDump(String fichero) {
        return fichero.replaceFirst("_\\d{8}_\\d{6}\\.(dump|sql)$", "");
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
                filas = filasPorDefecto(validacion);
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
        // Paso 8: tras exportar, se muestran también las BBDD objetivo registradas (USUARIO: solo las suyas).
        Object exportacion = sesion.getAttribute(SESION_EXPORTACION);
        model.addAttribute("exportacion", exportacion);
        if (exportacion != null) {
            try {
                List<BbddRegistrada> registro = api.listarRegistro();
                model.addAttribute("registro", permisos.veTodas() ? registro
                        : registro.stream().filter(r -> permisos.puedeUsar(r.nombre())).toList());
            } catch (ApiNoDisponibleException e) {
                model.addAttribute("registro", List.of());
            }
        }
        // Paso 9 (opcional, tras exportar): restaurar en el PostgreSQL de otro equipo.
        model.addAttribute("restauracion", sesion.getAttribute(SESION_RESTAURACION));
        Servidor ultimo = (Servidor) sesion.getAttribute(SESION_SERVIDOR);
        model.addAttribute("contrasenaGuardada", ultimo != null);
        if (exportacion != null && !model.containsAttribute("servidorForm")) {
            model.addAttribute("servidorForm", ServidorForm.de(ultimo));
        }
    }

    // Paso 3: filas que se proponen por defecto. Las tablas de nivel 0 empiezan con FILAS_POR_DEFECTO y cada
    // hija con el producto de las filas de sus padres (una FK por padre), para que quepan todas las
    // combinaciones de padres (p. ej. una PK compuesta de dos FK). Con un solo padre, las mismas filas que él.
    // Se recorre en orden de Kahn, así que los padres ya tienen sus filas. La FK a sí misma no cuenta.
    // Se limita a MAX_FILAS (el máximo que acepta la API).
    // Solo se calcula al proponerlas: si el usuario cambia un padre, las hijas no cambian.
    static Map<String, String> filasPorDefecto(ValidacionDdl validacion) {
        Map<String, Integer> minimos = new LinkedHashMap<>();
        // Se recorre en orden de Kahn, así que los padres ya tienen sus filas.
        for (TablaOrdenada t : validacion.orden()) {
            long producto = validacion.clavesForaneas().stream()
                    .filter(fk -> fk.tabla().equals(t.tabla()) && !fk.tablaPadre().equals(t.tabla())) // FK a sí misma no cuenta.
                    .mapToLong(fk -> minimos.getOrDefault(fk.tablaPadre(), FILAS_POR_DEFECTO))
                    .reduce((a, b) -> Math.min(a * b, MAX_FILAS)) // Se limita en cada paso para no desbordar.
                    .orElse(FILAS_POR_DEFECTO); // Nivel 0: sin padres.
            minimos.put(t.tabla(), (int) Math.min(producto, MAX_FILAS));
        }
        // Convertimos a Map<String, String> para que Thymeleaf lo muestre en el formulario.
        Map<String, String> filas = new LinkedHashMap<>();
        minimos.forEach((tabla, n) -> filas.put(tabla, String.valueOf(n)));
        return filas;
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
        sesion.removeAttribute(SESION_RESTAURACION);
    }
}
