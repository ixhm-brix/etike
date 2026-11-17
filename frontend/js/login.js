// Log in with a code sent by text message: phone number, then the code
// (and a name the first time). No account to create, no password.
// Admins and anyone else with a password can still use it below.
(function login() {
  const form = document.getElementById("code-login");
  const msg = document.getElementById("msg");
  const button = form.querySelector('button[type="submit"]');
  const codeField = document.getElementById("code-field");
  const nameField = document.getElementById("name-field");
  const devCode = document.getElementById("dev-code");
  const links = document.getElementById("code-links");
  const { phone, code, full_name: fullName } = form.elements;
  let step = "phone"; // "phone" -> "code"

  function done(data) {
    auth.save(data);
    location.href = auth.nextPage(auth.homeFor(data.user));
  }

  async function sendCode() {
    const data = await api.post("/auth/code", { phone: phone.value });
    step = "code";
    phone.readOnly = true;
    codeField.hidden = false;
    links.hidden = false;
    ui.say(msg, `We sent a code to ${phone.value}. It works for 10 minutes.`, "info");
    // Only on a laptop with no SMS set up: the server shows the code instead.
    devCode.hidden = !data.dev_code;
    if (data.dev_code) devCode.textContent = `Development mode, no SMS set up. Your code is ${data.dev_code}.`;
    code.value = "";
    code.focus();
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(form);
    if (step === "phone") {
      if (!phone.value.trim()) return ui.say(msg, "Enter your phone number.");
      try {
        await ui.busy(button, "Sending…", sendCode);
        // After busy() has put the old label back.
        button.textContent = "Log in";
      } catch (err) {
        ui.formError(form, msg, err);
      }
      return;
    }
    if (code.value.trim().length !== 6) return ui.say(msg, "Enter the 6-digit code from the text message.");
    const body = { phone: phone.value, code: code.value };
    if (!nameField.hidden) body.full_name = fullName.value;
    try {
      done(await ui.busy(button, "Logging in…", () => api.post("/auth/verify", body)));
    } catch (err) {
      if (err.code === "name_required") {
        // A new number: one more field and they're in.
        nameField.hidden = false;
        fullName.focus();
        ui.say(msg, "Welcome to ETIKE! Add your name to finish.", "info");
        return;
      }
      ui.formError(form, msg, err);
    }
  });

  document.getElementById("resend").addEventListener("click", async () => {
    try {
      await sendCode();
    } catch (err) {
      ui.say(msg, err.message);
    }
  });

  document.getElementById("change-number").addEventListener("click", () => {
    step = "phone";
    phone.readOnly = false;
    codeField.hidden = nameField.hidden = links.hidden = devCode.hidden = true;
    button.textContent = "Send me a code";
    msg.textContent = "";
    phone.focus();
  });

  // Password login, for admins and anyone who set a password.
  const pwForm = document.getElementById("login");
  const pwMsg = document.getElementById("password-msg");
  pwForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(pwForm);
    const { phone: pwPhone, password } = pwForm.elements;
    if (!pwPhone.value.trim() || !password.value) return ui.say(pwMsg, "Enter your phone number and password.");
    try {
      done(await ui.busy(pwForm.querySelector("button"), "Logging in…", () =>
        api.post("/auth/login", { phone: pwPhone.value, password: password.value })));
    } catch (err) {
      ui.formError(pwForm, pwMsg, err);
    }
  });
})();
