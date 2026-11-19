document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();
  document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.parentElement.querySelector("input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
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
  document.querySelectorAll(".auth-form").forEach((form) => form.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    let error = "";
    if (!email || !email.includes("@")) error = "Please enter a valid email address.";
    else if (!password) error = "Please enter your password.";
    else if (form.dataset.form === "register") {
      if (String(data.get("name") || "").trim().length < 2) error = "Please enter your full name.";
      else if (password.length < 8) error = "Use at least 8 characters for your password.";
      else if (password !== String(data.get("confirm") || "")) error = "Your passwords do not match.";
    }
    const message = form.querySelector(".form-message");
    message.textContent = error || "Form validation passed. Account submission will be enabled after the authentication API is integrated.";
    message.classList.toggle("is-error", Boolean(error));
    message.classList.toggle("is-success", !error);
  }));
});
