// Log in with phone number and password. Where the server allows it
// (DEMO_LOGIN, never on a public server), one click logs in as the Demo
// Traveller or the Demo Driver.
(function login() {
  const form = document.getElementById("login");
  const msg = document.getElementById("msg");
  const button = form.querySelector("button");
  auth.explainNext("to-register");

  function done(data) {
    auth.save(data);
    location.href = auth.nextPage(auth.homeFor(data.user));
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(form);
    const { phone, password } = form.elements;
    if (!phone.value.trim() || !password.value) {
      ui.say(msg, "Enter your phone number and password.");
      return;
    }
    try {
      done(await ui.busy(button, "Logging in…", () =>
        api.post("/auth/login", { phone: phone.value, password: password.value })));
    } catch (err) {
      ui.formError(form, msg, err);
    }
  });

  const demoMsg = document.getElementById("demo-msg");
  document.querySelectorAll(".demo-buttons button").forEach((b) => {
    b.addEventListener("click", async () => {
      try {
        done(await ui.busy(b, "Logging in…", () => api.post("/auth/demo", { role: b.dataset.role })));
      } catch (err) {
        ui.say(demoMsg, err.message);
      }
    });
  });
})();
