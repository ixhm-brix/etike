// Shared bits for the app pages: formatting, place lists and form errors.

const ui = (() => {
  const money = (n) => `RWF ${Number(n).toLocaleString("en-US")}`;

  // "2026-12-01T06:30" -> "Tue 1 Dec, 06:30". Times are Rwanda local time.
  function when(iso) {
    const d = new Date(iso);
    const day = d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
    return `${day}, ${clock(iso)}`;
  }
  const clock = (iso) => iso.slice(11, 16);
  const day = (iso) =>
    new Date(iso).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });

  const today = () => {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 10);
  };

  let placesCache = null;
  async function fillPlaces(select, placeholder, selected) {
    placesCache = placesCache || (await api.get("/places")).places;
    select.replaceChildren(new Option(placeholder, ""));
    placesCache.forEach((p) => select.append(new Option(p, p)));
    if (selected) select.value = selected;
  }

  // Show a message in a status box. tone: "error" or "info".
  function say(box, text, tone = "error") {
    box.dataset.tone = tone;
    box.textContent = text;
  }

  // Show an API error under the form, and mark the fields it names.
  function formError(form, box, err) {
    clearErrors(form);
    let marked = 0;
    Object.entries(err.fields || {}).forEach(([name, msg]) => {
      const input = form.elements[name];
      const field = input?.closest?.(".field");
      if (!field) return;
      marked += 1;
      field.classList.add("is-invalid");
      const note = document.createElement("span");
      note.className = "field-error";
      note.textContent = msg;
      field.append(note);
    });
    say(box, marked ? "Check the highlighted field and try again." : err.message);
  }

  function clearErrors(form) {
    form.querySelectorAll(".is-invalid").forEach((f) => f.classList.remove("is-invalid"));
    form.querySelectorAll(".field-error").forEach((n) => n.remove());
  }

  // Disable a button while a request runs, so it can't be sent twice.
  async function busy(button, label, work) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    try {
      return await work();
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function empty(title, text, link) {
    const box = el("div", "empty");
    box.append(el("strong", null, title), el("span", null, text));
    if (link) {
      const a = el("a", null, link.text);
      a.href = link.href;
      box.append(" ", a);
    }
    return box;
  }

  return { money, when, clock, day, today, fillPlaces, say, formError, clearErrors, busy, el, empty };
})();
