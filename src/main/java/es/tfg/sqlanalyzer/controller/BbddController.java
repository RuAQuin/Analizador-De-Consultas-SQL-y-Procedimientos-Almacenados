package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.api.ApiNoDisponibleException;
import es.tfg.sqlanalyzer.api.ApiPythonClient;
import es.tfg.sqlanalyzer.api.CreacionBbdd;
import es.tfg.sqlanalyzer.api.ErrorDdl;
import es.tfg.sqlanalyzer.api.PrototipoDatos;
import es.tfg.sqlanalyzer.api.TablaOrdenada;
import es.tfg.sqlanalyzer.api.ValidacionDdl;
import es.tfg.sqlanalyzer.form.CreacionBbddForm;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Módulo 1: generación de BBDD.
 * El estado del módulo (DDL validado, filas, prototipo y BBDD creada) se guarda en la sesión para
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
    }

    private void limpiarSesion(HttpSession sesion) {
        sesion.removeAttribute(SESION_FORM);
        sesion.removeAttribute(SESION_VALIDACION);
        sesion.removeAttribute(SESION_FILAS);
        sesion.removeAttribute(SESION_PROTOTIPO);
        sesion.removeAttribute(SESION_CREACION);
    }
}
