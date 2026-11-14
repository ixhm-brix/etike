// Pay for a pending booking with mobile money through Flutterwave.
// The amount always comes from the server. After "Pay with MoMo" we open
// Flutterwave's page in a new tab and check the status here until the
// payment succeeds, fails, or the seat hold runs out.
(async function payment() {
  const user = auth.require("passenger");
  if (!user) return;

  const bookingId = new URLSearchParams(location.search).get("booking");
  const loading = document.getElementById("loading");
  const paySection = document.getElementById("pay");
  const form = document.getElementById("pay-form");
  const waiting = document.getElementById("waiting");
  const countdown = document.getElementById("countdown");
  const msg = document.getElementById("msg");
  const button = form.querySelector("button");

  const POLL_MS = 4000;
  let pollTimer = null;
  let clockTimer = null;

  let state;
  try {
    state = await api.get(`/payments/${encodeURIComponent(bookingId)}/status`);
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.status === 404 ? "We couldn't find this booking." : err.message);
    return;
  }
  loading.hidden = true;
  show(state);

  function show({ booking, payment }) {
    document.getElementById("subtitle").textContent =
      `${booking.origin} to ${booking.destination}, ${ui.when(booking.departure_time)}`;

    if (booking.status === "confirmed") return finish("paid", booking);
    if (booking.status === "cancelled") {
      return finish(payment?.status === "failed" ? "failed" : "expired", booking);
    }

    // Pending: show what is owed and how long the seats are held.
    paySection.hidden = false;
    fillSummary(document.getElementById("summary"), [
      ["With", booking.operator],
      ["Seats", String(booking.seats_booked)],
      ["To pay", ui.money(booking.total_price), true],
    ]);
    startClock(booking.expires_at);

    if (payment && payment.status === "pending") {
      waitFor(payment);
    } else {
      form.elements.phone.value = localPhone(user.phone);
      document.getElementById("email-field").hidden = Boolean(user.email);
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(form);
    const body = { booking_id: Number(bookingId), phone: form.elements.phone.value };
    if (form.elements.email.value) body.email = form.elements.email.value;
    // Open the tab now, while the click still counts as the user's action,
    // so pop-up blockers allow it. We point it at Flutterwave once we know the URL.
    const tab = window.open("", "_blank");
    try {
      const { payment: p } = await ui.busy(button, "Starting payment…", () =>
        api.post("/payments", body),
      );
      if (tab) tab.location.href = p.checkout_url;
      waitFor(p);
    } catch (err) {
      if (tab) tab.close();
      ui.formError(form, msg, err);
    }
  });

  function waitFor(p) {
    form.hidden = true;
    waiting.hidden = false;
    msg.textContent = "";
    const link = document.getElementById("checkout-link");
    if (p.checkout_url) link.href = p.checkout_url;
    else link.hidden = true;
    clearInterval(pollTimer);
    pollTimer = setInterval(poll, POLL_MS);
  }

  async function poll() {
    try {
      const next = await api.get(`/payments/${encodeURIComponent(bookingId)}/status`);
      if (next.booking.status !== "pending") {
        clearInterval(pollTimer);
        show(next);
      }
    } catch (err) {
      // A missed check is fine; the next one tries again.
    }
  }

  function startClock(expiresAt) {
    const end = new Date(expiresAt).getTime();
    clearInterval(clockTimer);
    const tick = () => {
      const left = Math.max(0, end - Date.now());
      const m = Math.floor(left / 60000);
      const s = String(Math.floor((left % 60000) / 1000)).padStart(2, "0");
      countdown.textContent = `Your seats are held for ${m}:${s}`;
      countdown.classList.toggle("is-urgent", left < 120000);
      if (left === 0) {
        clearInterval(clockTimer);
        countdown.textContent = "Time is up. Checking your booking…";
        poll();
      }
    };
    tick();
    clockTimer = setInterval(tick, 1000);
  }

  function finish(outcome, booking) {
    clearInterval(pollTimer);
    clearInterval(clockTimer);
    paySection.hidden = true;
    const title = document.getElementById("title");
    const links = document.getElementById("result-links");
    links.replaceChildren();
    const link = (href, text) => {
      const a = ui.el("a", null, text);
      a.href = href;
      links.append(a, " ");
    };

    if (outcome === "paid") {
      title.textContent = "You're booked";
      fillSummary(document.getElementById("receipt"), [
        ["Booking number", `#${booking.booking_id}`],
        ["With", booking.operator],
        ["Seats", String(booking.seats_booked)],
        ["Paid", ui.money(booking.total_price), true],
      ]);
      ui.say(msg, "Payment received. Your booking is confirmed.", "info");
      link("/bookings.html", "See your ticket in My bookings");
    } else if (outcome === "failed") {
      title.textContent = "Payment didn't go through";
      ui.say(msg, "The payment failed, so your seats were released. You can book again.");
      link("/search.html", "Search again");
    } else {
      title.textContent = "Booking expired";
      ui.say(msg, "The time to pay ran out, so your seats were released. You can book again.");
      link("/search.html", "Search again");
    }
    document.getElementById("result").hidden = false;
    document.getElementById("receipt").hidden = outcome !== "paid";
  }

  function fillSummary(dl, rows) {
    dl.replaceChildren(
      ...rows.map(([k, v, total]) => {
        const row = ui.el("div", total ? "summary-total" : null);
        row.append(ui.el("dt", null, k), ui.el("dd", null, v));
        return row;
      }),
    );
  }

  // "+250781234567" -> "0781234567"
  function localPhone(phone) {
    return phone.startsWith("+250") ? `0${phone.slice(4)}` : phone;
  }
})();
