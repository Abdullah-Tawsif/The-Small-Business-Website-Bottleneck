
document.addEventListener("DOMContentLoaded", () => {
  // Initialize Lucide icons.
  if (window.lucide) {
    window.lucide.createIcons();
  }

  // --------------------------------------------------
  // 1. PASSWORD VISIBILITY TOGGLE
  // --------------------------------------------------

  document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.parentElement.querySelector("input");

      if (!input) return;

      const show = input.type === "password";

      input.type = show ? "text" : "password";

      button.setAttribute(
        "aria-label",
        show ? "Hide password" : "Show password"
      );

      button.textContent = show ? "Hide" : "Show";
    });
  });

  // --------------------------------------------------
  // 2. MOBILE NAVIGATION
  // --------------------------------------------------

  const menu = document.querySelector(".menu-toggle");
  const links = document.querySelector(".nav-links");

  if (menu && links) {
    menu.addEventListener("click", () => {
      const open = menu.getAttribute("aria-expanded") !== "true";

      menu.setAttribute("aria-expanded", String(open));
      links.classList.toggle("is-open", open);
    });
  }

  // --------------------------------------------------
  // 3. FORM MESSAGE HELPERS
  // --------------------------------------------------

  function showMessage(form, message, type = "error") {
    const messageElement = form.querySelector(".form-message");

    if (!messageElement) return;

    messageElement.textContent = message;

    messageElement.classList.toggle(
      "is-error",
      type === "error"
    );

    messageElement.classList.toggle(
      "is-success",
      type === "success"
    );
  }

  function getBackendError(data, statusCode) {
    if (data && typeof data.detail === "string") {
      return data.detail;
    }

    if (Array.isArray(data?.detail)) {
      return data.detail
        .map((error) => error.msg || "Invalid input.")
        .join(" ");
    }

    if (typeof data?.message === "string") {
      return data.message;
    }

    return `Request failed (${statusCode}). Please check your information and try again.`;
  }

  // --------------------------------------------------
  // 4. AUTHENTICATION FORMS
  // --------------------------------------------------

  document.querySelectorAll(".auth-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();

      const submitButton = form.querySelector(
        'button[type="submit"], input[type="submit"]'
      );

      const formType = form.dataset.form;

      const formData = new FormData(form);

      const name = String(
        formData.get("name") || ""
      ).trim();

      const email = String(
        formData.get("email") || ""
      ).trim();

      const password = String(
        formData.get("password") || ""
      );

      const confirmPassword = String(
        formData.get("confirm") || ""
      );

      // ------------------------------------------------
      // 5. CLIENT-SIDE VALIDATION
      // ------------------------------------------------

      let error = "";

      const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

      if (!email || !emailPattern.test(email)) {
        error = "Please enter a valid email address.";
      } else if (!password) {
        error = "Please enter your password.";
      } else if (formType === "register") {
        if (name.length < 2) {
          error = "Please enter your full name.";
        } else if (password.length < 10) {
          error = "Your password must contain at least 10 characters.";
        } else if (password !== confirmPassword) {
          error = "Your passwords do not match.";
        }
      }

      if (error) {
        showMessage(form, error, "error");
        return;
      }

      // ------------------------------------------------
      // 6. PREPARE API REQUEST
      // ------------------------------------------------

      const isRegistration = formType === "register";

      const endpoint = isRegistration
        ? "/api/auth/register"
        : "/api/auth/login";

      const requestBody = isRegistration
        ? {
            full_name: name,
            email: email,
            password: password
          }
        : {
            email: email,
            password: password
          };

      // ------------------------------------------------
      // 7. DISABLE BUTTON WHILE REQUEST RUNS
      // ------------------------------------------------

      const originalButtonText = submitButton
        ? (
            submitButton.tagName === "INPUT"
              ? submitButton.value
              : submitButton.textContent
          )
        : "";

      if (submitButton) {
        submitButton.disabled = true;
        submitButton.setAttribute("aria-busy", "true");

        if (submitButton.tagName === "INPUT") {
          submitButton.value = isRegistration
            ? "Creating account..."
            : "Signing in...";
        } else {
          submitButton.textContent = isRegistration
            ? "Creating account..."
            : "Signing in...";
        }
      }

      showMessage(
        form,
        isRegistration
          ? "Creating your account..."
          : "Signing you in...",
        "success"
      );

      // ------------------------------------------------
      // 8. SUBMIT TO AUTHENTICATION API
      // ------------------------------------------------

      try {
        const response = await fetch(endpoint, {
          method: "POST",

          credentials: "same-origin",

          headers: {
            "Content-Type": "application/json",
            "Accept": "application/json"
          },

          body: JSON.stringify(requestBody)
        });

        // Safely read the backend response.
        const data = await response.json().catch(() => ({}));

        // ------------------------------------------------
        // 9. HANDLE BACKEND ERRORS
        // ------------------------------------------------

        if (!response.ok) {
          const backendError = getBackendError(
            data,
            response.status
          );

          showMessage(
            form,
            backendError,
            "error"
          );

          return;
        }

        // ------------------------------------------------
        // 10. HANDLE SUCCESSFUL AUTHENTICATION
        // ------------------------------------------------

        showMessage(
          form,
          data.message || (
            isRegistration
              ? "Your account was created successfully!"
              : "You have signed in successfully!"
          ),
          "success"
        );

        // Redirect to the URL supplied by the backend.
        const redirectUrl = data.redirect_url;

        if (typeof redirectUrl === "string" && redirectUrl.trim()) {
          window.location.assign(redirectUrl);
        } else {
          showMessage(
            form,
            "Authentication succeeded, but the server did not provide a redirect URL.",
            "error"
          );
        }

      } catch (error) {
        // Network errors, server connection failures, etc.
        console.error(
          "Authentication request failed:",
          error
        );

        showMessage(
          form,
          "Unable to connect to the server. Please check your internet connection and try again.",
          "error"
        );

      } finally {
        // ------------------------------------------------
        // 11. RESTORE SUBMIT BUTTON
        // ------------------------------------------------

        if (submitButton) {
          submitButton.disabled = false;
          submitButton.removeAttribute("aria-busy");

          if (submitButton.tagName === "INPUT") {
            submitButton.value = originalButtonText;
          } else {
            submitButton.textContent = originalButtonText;
          }
        }
      }
    });
  });
});
