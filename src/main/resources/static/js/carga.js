// Paso 6 del módulo 1: reloj de la carga de datos.
// El formulario de inserción se envía como siempre; si la respuesta tarda más de ESPERA, aparece el reloj
// con el tiempo que lleva y, cada segundo, se pregunta a la WebApp cómo va la inserción (fase, tabla, filas).
// Al llegar la respuesta, el navegador carga la página nueva y el reloj desaparece solo.
(function () {
    "use strict";

    const ESPERA = 1000; // ms sin respuesta antes de mostrar el reloj.
    const CADA = 1000;   // ms entre consultas del progreso.

    const form = document.querySelector("form[data-progreso]");
    const reloj = document.getElementById("reloj-carga");
    if (!form || !reloj) {
        return;
    }
    const tiempo = reloj.querySelector(".reloj-tiempo");
    const texto = reloj.querySelector(".reloj-texto");
    const barra = reloj.querySelector(".reloj-barra");
    const queda = reloj.querySelector(".reloj-queda");
    const numero = new Intl.NumberFormat("es-ES");

    // 75 s → «1:15».
    function minutos(segundos) {
        const s = Math.floor(segundos);
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
    }

    // Barra sin valor = animación de «trabajando» (no se sabe cuánto falta).
    function sinPorcentaje(mensaje) {
        texto.textContent = mensaje;
        barra.removeAttribute("value");
        queda.textContent = "";
    }

    form.addEventListener("submit", function () {
        const inicio = Date.now();
        let fase = null;
        let inicioFase = 0;
        form.querySelector("button[type=submit]").disabled = true; // Evita enviar la carga dos veces.

        // Estimación de lo que queda de la fase, con la velocidad que lleva en ella.
        function estimar(p) {
            const segundos = (Date.now() - inicioFase) / 1000;
            if (p.hechas <= 0 || p.hechas >= p.total || segundos < 1) {
                return "";
            }
            return "quedan ~" + minutos(segundos * (p.total - p.hechas) / p.hechas) + " de esta fase";
        }

        function mostrar(p) {
            if (p.fase !== fase) {
                fase = p.fase;
                inicioFase = Date.now();
            }
            const filas = numero.format(p.hechas) + " / " + numero.format(p.total) + " filas";
            const porcentaje = p.total > 0 ? Math.floor(100 * p.hechas / p.total) : 100;
            if (p.fase === "escribiendo" && p.hechas >= p.total) {
                sinPorcentaje("Fase 2 de 2 · Confirmando la transacción en PostgreSQL…");
                return;
            }
            texto.textContent = p.fase === "generando"
                ? "Fase 1 de 2 · Generando tuplas · " + filas + " (" + porcentaje + " %)"
                : "Fase 2 de 2 · Escribiendo «" + p.tabla + "» · " + filas + " (" + porcentaje + " %)";
            barra.max = p.total;
            barra.value = p.hechas;
            queda.textContent = estimar(p);
        }

        async function actualizar() {
            tiempo.textContent = minutos((Date.now() - inicio) / 1000);
            try {
                const r = await fetch(form.dataset.progreso, {headers: {"Accept": "application/json"}});
                if (r.status === 200) {
                    mostrar(await r.json());
                } else if (fase === null) {
                    // 204: aún no ha empezado (se están comprobando el DDL y el prototipo).
                    sinPorcentaje("Preparando la carga…");
                }
            } catch (e) {
                // Sin respuesta de la WebApp: se mantiene lo último que se ha mostrado.
            }
        }

        setTimeout(function () {
            reloj.hidden = false;
            actualizar();
            setInterval(actualizar, CADA);
        }, ESPERA);
    });
})();
