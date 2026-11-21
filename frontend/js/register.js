// Create a passenger or driver account: name, phone and password only.
// Drivers then fill in their official details and upload their documents
// on the driver page, and an admin approves them.
(function register() {
  const form = document.getElementById("register");
  const msg = document.getElementById("msg");
  const button = form.querySelector("button");
  const driverHint = document.getElementById("driver-hint");
  auth.explainNext("to-login");

  function sync() {
    driverHint.hidden = form.elements.role.value !== "driver";
  }
  if (new URLSearchParams(location.search).get("role") === "driver") form.elements.role.value = "driver";
  form.addEventListener("change", sync);
  sync();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(form);
    const f = form.elements;
    const body = {
      role: f.role.value,
      full_name: f.full_name.value,
      phone: f.phone.value,
      email: f.email.value || undefined,
      password: f.password.value,
    };
    try {
      const data = await ui.busy(button, "Creating account…", () => api.post("/auth/register", body));
      auth.save(data);
      location.href = auth.nextPage(auth.homeFor(data.user));
    } catch (err) {
      ui.formError(form, msg, err);
    }
  });
})();
