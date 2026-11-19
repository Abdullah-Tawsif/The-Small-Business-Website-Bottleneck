document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();
  document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.parentElement.querySelector("input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide" : "Show";
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
  const menu = document.querySelector(".menu-toggle");
  const links = document.querySelector(".nav-links");
  if (menu && links) menu.addEventListener("click", () => {
    const open = menu.getAttribute("aria-expanded") !== "true";
    menu.setAttribute("aria-expanded", String(open));
    links.classList.toggle("is-open", open);
  });

  document.querySelectorAll(".auth-form").forEach((form) => form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const message = form.querySelector(".form-message");
    const button = form.querySelector('button[type="submit"]');
    const payload = { email: String(data.get("email") || "").trim(), password: String(data.get("password") || "") };
    if (form.dataset.form === "register") {
      payload.full_name = String(data.get("name") || "").trim();
      if (payload.password !== String(data.get("confirm") || "")) {
        message.textContent = "Your passwords do not match.";
        message.className = "form-message is-error";
        return;
      }
    }
    message.textContent = "";
    message.className = "form-message";
    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = "Please wait…";
    try {
      const endpoint = form.dataset.form === "register" ? "/api/auth/register" : "/api/auth/login";
      const response = await fetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify(payload) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Unable to complete your request.");
      message.textContent = result.message || "Success.";
      message.className = "form-message is-success";
      window.location.assign(result.redirect_url || "/dashboard");
    } catch (error) {
      message.textContent = error.message || "Something went wrong. Please try again.";
      message.className = "form-message is-error";
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }));
});
