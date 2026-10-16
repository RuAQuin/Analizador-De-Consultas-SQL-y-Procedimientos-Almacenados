package es.tfg.sqlanalyzer.controller;

import es.tfg.sqlanalyzer.form.UsuarioForm;
import es.tfg.sqlanalyzer.model.Usuario;
import es.tfg.sqlanalyzer.service.UsuarioService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
import org.springframework.util.StringUtils;

/** Objetivo: alta, edición y baja de usuarios (solo ADMIN). */
@Controller
@RequestMapping("/usuarios")
public class UsuarioController {

    private final UsuarioService usuarioService;

    public UsuarioController(UsuarioService usuarioService) {
        this.usuarioService = usuarioService;
    }

    @ModelAttribute("activePage")
    public String activePage() {
        return "usuarios";
    }

    @GetMapping
    public String listar(Model model) {
        model.addAttribute("usuarios", usuarioService.listarTodos());
        return "usuarios";
    }

    @GetMapping("/nuevo")
    public String nuevo(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new UsuarioForm());
        }
        model.addAttribute("esNuevo", true);
        return "usuario-form";
    }

    @PostMapping
    public String crear(@Valid @ModelAttribute("form") UsuarioForm form,
                         BindingResult result,
                         Model model,
                         RedirectAttributes ra) {
        if (!StringUtils.hasText(form.getPassword())) {
            result.rejectValue("password", "obligatoria", "La contraseña es obligatoria");
        } else if (form.getPassword().length() < 6) {
            result.rejectValue("password", "corta", "La contraseña debe tener al menos 6 caracteres");
        }
        if (!result.hasFieldErrors("username") && usuarioService.existeUsername(form.getUsername())) {
            result.rejectValue("username", "duplicado", "Ese nombre de usuario ya está en uso");
        }
        if (result.hasErrors()) {
            model.addAttribute("esNuevo", true);
            return "usuario-form";
        }

        usuarioService.crear(form);
        ra.addFlashAttribute("aviso", "Usuario «" + form.getUsername() + "» creado.");
        return "redirect:/usuarios";
    }

    @GetMapping("/{id}/editar")
    public String editar(@PathVariable Long id, Model model) {
        if (!model.containsAttribute("form")) {
            Usuario usuario = usuarioService.obtener(id);
            UsuarioForm form = new UsuarioForm();
            form.setId(usuario.getId());
            form.setUsername(usuario.getUsername());
            form.setRol(usuario.getRol());
            form.setHabilitado(usuario.isHabilitado());
            model.addAttribute("form", form);
        }
        model.addAttribute("esNuevo", false);
        return "usuario-form";
    }

    @PostMapping("/{id}")
    public String actualizar(@PathVariable Long id,
                              @Valid @ModelAttribute("form") UsuarioForm form,
                              BindingResult result,
                              Model model,
                              RedirectAttributes ra) {
        if (StringUtils.hasText(form.getPassword()) && form.getPassword().length() < 6) {
            result.rejectValue("password", "corta", "La contraseña debe tener al menos 6 caracteres");
        }
        if (!result.hasFieldErrors("username") && usuarioService.existeUsernameDeOtro(id, form.getUsername())) {
            result.rejectValue("username", "duplicado", "Ese nombre de usuario ya está en uso");
        }
        if (result.hasErrors()) {
            form.setId(id);
            model.addAttribute("esNuevo", false);
            return "usuario-form";
        }

        try {
            usuarioService.actualizar(id, form);
        } catch (IllegalStateException ex) {
            ra.addFlashAttribute("error", ex.getMessage());
            return "redirect:/usuarios";
        }
        ra.addFlashAttribute("aviso", "Usuario «" + form.getUsername() + "» actualizado.");
        return "redirect:/usuarios";
    }

    @PostMapping("/{id}/eliminar")
    public String eliminar(@PathVariable Long id, Authentication auth, RedirectAttributes ra) {
        Usuario usuario = usuarioService.obtener(id);
        if (usuario.getUsername().equals(auth.getName())) {
            ra.addFlashAttribute("error", "No puedes eliminar tu propio usuario.");
            return "redirect:/usuarios";
        }

        try {
            usuarioService.eliminar(id);
            ra.addFlashAttribute("aviso", "Usuario «" + usuario.getUsername() + "» eliminado.");
        } catch (IllegalStateException ex) {
            ra.addFlashAttribute("error", ex.getMessage());
        }
        return "redirect:/usuarios";
    }
}
