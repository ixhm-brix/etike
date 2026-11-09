// Log in with phone number and password.
(function login() {
  const form = document.getElementById("login");
  const msg = document.getElementById("msg");
  const button = form.querySelector("button");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(form);
    const { phone, password } = form.elements;
    if (!phone.value.trim() || !password.value) {
      ui.say(msg, "Enter your phone number and password.");
      return;
    }
    try {
      const data = await ui.busy(button, "Logging in…", () =>
        api.post("/auth/login", { phone: phone.value, password: password.value }),
      );
      auth.save(data);
      location.href = auth.nextPage(auth.homeFor(data.user));
    } catch (err) {
      ui.formError(form, msg, err);
    }
  });
})();
