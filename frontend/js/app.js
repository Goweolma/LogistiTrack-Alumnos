// TODO(ALUMNO-6): reemplazar esta vista base por formulario, seguimiento y tablero.
async function checkPlatform() {
  const badge = document.querySelector("#status");
  const message = document.querySelector("#message");
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    badge.textContent = "BASE LISTA";
    badge.className = "badge ok";
    message.textContent = data.message;
  } catch (error) {
    badge.textContent = "SIN CONEXIÓN";
    badge.className = "badge error";
    message.textContent = `No fue posible contactar la API: ${error.message}`;
  }
}

checkPlatform();
