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

  // A date with its year, e.g. "30 Jun 2027" (document expiry dates).
  const date = (iso) =>
    new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
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

  // Open a private file (a driver's document) in a new tab. It needs the
  // login token, so it is fetched first and opened from a local copy.
  async function openFile(path, button, box) {
    const tab = window.open("", "_blank");
    try {
      const blob = await busy(button, "…", () => api.file(path));
      const url = URL.createObjectURL(blob);
      if (tab) tab.location = url;
      else location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      if (tab) tab.close();
      say(box, err.message);
    }
  }

  // A banner at the top of the screen that confirms something happened,
  // e.g. "Your ride is booked". Hides itself after a few seconds.
  function toast(title, text = "", tone = "info") {
    document.querySelector(".toast")?.remove();
    const box = el("div", `toast is-hidden${tone === "good" ? " is-good" : ""}`);
    box.setAttribute("role", "status");
    box.append(title);
    if (text) box.append(el("span", null, text));
    document.body.append(box);
    requestAnimationFrame(() => requestAnimationFrame(() => box.classList.remove("is-hidden")));
    setTimeout(() => {
      box.classList.add("is-hidden");
      setTimeout(() => box.remove(), 400);
    }, 6000);
    box.addEventListener("click", () => box.classList.add("is-hidden"));
  }

  // Call, WhatsApp and Message buttons for the other person on a ride.
  // phone is "+2507…" (or null once the contact window has closed); unread
  // is the number of new messages, shown on the Message button.
  function contact({ phone, bookingId, unread = 0, name = "" }) {
    const box = el("div", "contact");
    if (phone) {
      const call = el("a", "btn-gray btn-sm", "Call");
      call.href = `tel:${phone}`;
      call.setAttribute("aria-label", `Call ${name}`.trim());
      const wa = el("a", "btn-gray btn-sm", "WhatsApp");
      wa.href = `https://wa.me/${phone.replace(/^\+/, "")}`;
      wa.target = "_blank";
      wa.rel = "noopener";
      wa.setAttribute("aria-label", `WhatsApp ${name}`.trim());
      box.append(call, wa);
    }
    const chat = el("a", "btn-black btn-sm", "Message");
    chat.href = `/chat.html?booking=${bookingId}`;
    if (unread) {
      chat.append(el("span", "badge", String(unread)));
      chat.setAttribute("aria-label", `Message ${name}, ${unread} new`.trim());
    }
    box.append(chat);
    return box;
  }

  // What passengers say about a driver: average, count, then each review
  // (stars, comment, "Divine I. · Kigali to Huye · 12 Nov"). Shows `limit`
  // at first, with a button for the rest.
  function reviews(data, { limit = 3, empty = "No reviews yet." } = {}) {
    const box = el("section", "reviews");
    const head = el("div", "reviews-head");
    head.append(el("strong", null, "What passengers say"));
    if (data.count) {
      head.append(el("span", null, `★ ${data.avg_rating.toFixed(1)} · ${data.count} review${data.count > 1 ? "s" : ""}`));
    }
    box.append(head);
    if (!data.recent.length) {
      box.append(el("p", "reviews-empty", empty));
      return box;
    }
    const list = el("ul", "reviews-list");
    data.recent.forEach((r, i) => {
      const li = el("li", "review");
      const stars = el("span", "review-stars", "★".repeat(r.score) + "☆".repeat(5 - r.score));
      stars.setAttribute("aria-label", `${r.score} out of 5`);
      li.append(stars);
      if (r.comment) li.append(el("p", null, r.comment));
      li.append(el("span", "review-by", [r.by, r.route, date(r.created_at)].filter(Boolean).join(" · ")));
      li.hidden = i >= limit;
      list.append(li);
    });
    box.append(list);
    if (data.recent.length > limit) {
      const more = el("button", "btn-gray btn-sm", `Show all ${data.recent.length} reviews`);
      more.type = "button";
      more.addEventListener("click", () => {
        list.querySelectorAll("li[hidden]").forEach((li) => { li.hidden = false; });
        more.remove();
      });
      box.append(more);
    }
    return box;
  }

  return { money, when, clock, day, date, today, toast, contact, reviews, fillPlaces, say, formError, clearErrors, busy, el, empty, openFile };
})();
