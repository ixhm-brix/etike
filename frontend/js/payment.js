// Pay with MTN MoMo: a ride once the driver has ended it, or (future
// phase) a pending bus ticket before travel.
// The amount always comes from the server. After "Pay with MoMo" the
// passenger approves on their phone with their MoMo PIN, and this page
// checks the status until the payment succeeds, fails, is declined, or the
// seat hold runs out.
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

  function show({ booking, payment, provider }) {
    document.getElementById("subtitle").textContent =
      `${booking.origin} to ${booking.destination}, ${ui.when(booking.departure_time)}`;

    if (booking.pay_after_ride) return showRide(booking, payment, provider);
    if (booking.status === "confirmed") return finish("paid", booking);
    if (booking.status === "cancelled") return finish(whyCancelled(payment), booking);

    // Pending: show what is owed and how long the seats are held.
    paySection.hidden = false;
    fillSummary(document.getElementById("summary"), [
      ["With", booking.operator],
      ["Seats", String(booking.seats_booked)],
      ["To pay", ui.money(booking.total_price), true],
    ]);
    // The MoMo sandbox can't charge francs, so say what it will show instead.
    const note = document.getElementById("sandbox-note");
    if (provider && provider.currency !== "RWF") {
      note.hidden = false;
      note.textContent = `Sandbox test currency: MoMo will show ${provider.currency} `
        + `${booking.total_price.toLocaleString("en-US")}. No real money moves.`;
    }
    startClock(booking.expires_at);

    if (payment && payment.status === "pending") waitForApproval();
    else if (/^\+2507[89]/.test(user.phone)) form.elements.phone.value = localPhone(user.phone);
  }

  // A ride: paid after the driver ends it. No seat hold, and a failed
  // payment can simply be tried again.
  function showRide(booking, payment, provider) {
    document.getElementById("title").textContent = "Pay for your ride";
    countdown.hidden = true;
    if (payment?.status === "success") return finishRide(booking);
    if (booking.status !== "confirmed") return finish("expired", booking);
    if (!booking.can_pay && payment?.status !== "pending") {
      paySection.hidden = true;
      ui.say(msg, booking.ride_progress === "in_progress"
        ? "Your ride is under way. You pay once the driver ends it."
        : "You pay once the driver ends the ride. We'll show \"Pay now\" in My bookings.", "info");
      return;
    }
    paySection.hidden = false;
    form.hidden = false;
    waiting.hidden = true;
    fillSummary(document.getElementById("summary"), [
      ["Ride", `${booking.origin} to ${booking.destination}`],
      ["Driver", booking.operator],
      ["Seats", String(booking.seats_booked)],
      ["To pay", ui.money(booking.total_price), true],
    ]);
    const note = document.getElementById("sandbox-note");
    if (provider && provider.currency !== "RWF") {
      note.hidden = false;
      note.textContent = `Sandbox test currency: MoMo will show ${provider.currency} `
        + `${booking.total_price.toLocaleString("en-US")}. No real money moves.`;
    }
    if (payment?.status === "pending") return waitForApproval();
    if (payment?.status === "failed") {
      ui.say(msg, `${ENDINGS[whyCancelled(payment)][0]}. You were not charged. Please try again.`);
    }
    if (!form.elements.phone.value && /^\+2507[89]/.test(user.phone)) {
      form.elements.phone.value = localPhone(user.phone);
    }
  }

  function finishRide(booking) {
    clearInterval(pollTimer);
    paySection.hidden = true;
    document.getElementById("title").textContent = "Thank you!";
    fillSummary(document.getElementById("receipt"), [
      ["Booking number", `#${booking.booking_id}`],
      ["Ride", `${booking.origin} to ${booking.destination}`],
      ["Driver", booking.operator],
      ["Paid", ui.money(booking.total_price), true],
    ]);
    ui.say(msg, "Payment received. Your driver has been told.", "info");
    ui.toast("Payment received", `${ui.money(booking.total_price)} paid to ${booking.operator}.`, "good");
    const links = document.getElementById("result-links");
    links.replaceChildren();
    const a = ui.el("a", null, "Rate your driver in My bookings");
    a.href = "/bookings.html";
    links.append(a);
    document.getElementById("result").hidden = false;
    document.getElementById("receipt").hidden = false;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(form);
    ui.say(msg, ""); // drop the last attempt's error while this one is sent
    if (!form.elements.phone.value.trim()) {
      ui.say(msg, "Enter the MTN MoMo number you want to pay with.");
      return;
    }
    const body = { booking_id: Number(bookingId), phone: form.elements.phone.value };
    try {
      // MoMo can take a while to answer, so wait longer than usual.
      await ui.busy(button, "Sending the request to your phone…", () =>
        api.post("/payments", body, { timeoutMs: 45000 }),
      );
      waitForApproval();
    } catch (err) {
      if (err.status === 0) {
        // We don't know if the request got through; the status tells us.
        const next = await api.get(`/payments/${encodeURIComponent(bookingId)}/status`).catch(() => null);
        if (next?.payment?.status === "pending") return waitForApproval();
      }
      ui.formError(form, msg, err);
    }
  });

  function waitForApproval() {
    form.hidden = true;
    waiting.hidden = false;
    msg.textContent = "";
    clearInterval(pollTimer);
    pollTimer = setInterval(poll, POLL_MS);
  }

  async function poll() {
    try {
      const next = await api.get(`/payments/${encodeURIComponent(bookingId)}/status`);
      const settled = next.booking.pay_after_ride
        ? next.payment?.status !== "pending"
        : next.booking.status !== "pending";
      if (settled) {
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

  // Why a booking was cancelled: "rejected", "timeout", "failed" or "expired".
  function whyCancelled(payment) {
    if (payment?.status !== "failed") return "expired";
    const reason = payment.failure_reason || "";
    if (reason.includes("REJECTED")) return "rejected";
    if (reason === "EXPIRED" || reason.includes("TIMEOUT")) return "timeout";
    return "failed";
  }

  const ENDINGS = {
    rejected: ["Payment declined",
      "You declined the payment on your phone, so your seats were released. You were not charged."],
    timeout: ["Payment not approved in time",
      "The request on your phone ran out before it was approved, so your seats were released. You were not charged."],
    failed: ["Payment didn't go through",
      "MoMo could not complete the payment, so your seats were released. Check your balance and number, then book again."],
    expired: ["Booking expired",
      "The time to pay ran out, so your seats were released. You can book again."],
  };

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
        [booking.seat_numbers.length > 1 ? "Seats" : "Seat",
          booking.seat_numbers.join(", ") || String(booking.seats_booked)],
        ["Paid", ui.money(booking.total_price), true],
      ]);
      ui.say(msg, "Payment received. Your booking is confirmed.", "info");
      link(`/ticket.html?booking=${booking.booking_id}`, "Show my ticket");
      link("/bookings.html", "My bookings");
    } else {
      const [heading, text] = ENDINGS[outcome];
      title.textContent = heading;
      ui.say(msg, text);
      link(`/?origin=${encodeURIComponent(booking.origin)}&destination=${encodeURIComponent(booking.destination)}`,
        "Book again");
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
