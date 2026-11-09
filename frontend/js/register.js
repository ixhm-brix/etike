// Create a passenger or driver account. Drivers also give their licence
// number; an admin approves it before they can post rides.
(function register() {
  const form = document.getElementById("register");
  const msg = document.getElementById("msg");
  const button = form.querySelector("button");
  const licence = document.getElementById("licence-field");
  const licenceHint = document.getElementById("licence-hint");

  function sync() {
    const isDriver = form.elements.role.value === "driver";
    licence.hidden = !isDriver;
    licenceHint.hidden = !isDriver;
  }
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
    if (body.role === "driver") body.license_number = f.license_number.value;
    try {
      const data = await ui.busy(button, "Creating account…", () => api.post("/auth/register", body));
      auth.save(data);
      location.href = auth.nextPage(auth.homeFor(data.user));
    } catch (err) {
      ui.formError(form, msg, err);
    }
  });
})();
