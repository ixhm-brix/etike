// The logged-in passenger's bookings: pay pending bus tickets, see the
// ticket for confirmed ones, cancel (until the cut-off before departure),
// follow a refund, and rate the driver after a ride.
(async function bookings() {
  if (!auth.require()) return;
  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");

  const TYPE = { bus: "Bus", shared: "Shared seat", private: "Private car" };
  const STATUS = { pending: "Waiting for payment", confirmed: "Confirmed", cancelled: "Cancelled" };

  const justBooked = new URLSearchParams(location.search).get("new");

  try {
    const { bookings: items } = await api.get("/bookings/mine");
    loading.hidden = true;
    const fresh = items.find((b) => String(b.booking_id) === justBooked && b.status === "confirmed");
    if (fresh) {
      ui.say(msg, `You're booked with ${fresh.operator}. Pay the driver ${ui.money(fresh.total_price)} `
        + "during or after the ride.", "info");
    }
    if (!items.length) {
      list.replaceWith(ui.empty("No bookings yet", "When you book a trip it shows here.", {
        href: "/search.html", text: "Find a trip",
      }));
      return;
    }
    list.append(...items.map(row));
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.message);
  }

  function row(b) {
    const li = ui.el("li", "result");
    li.append(
      ui.el("span", "result-time", `${b.origin} to ${b.destination}`),
      ui.el("span", "result-price", ui.money(b.total_price)),
      ui.el("span", "result-meta", `${ui.when(b.departure_time)} · ${TYPE[b.booking_type]} · ${b.operator}`),
      ui.el("span", "result-note", `${b.seats_booked} seat${b.seats_booked > 1 ? "s" : ""}`),
    );

    if (b.status === "confirmed") li.append(ticket(b));

    const actions = ui.el("div", "result-actions");
    actions.append(ui.el("span", `status status-${b.status}`, STATUS[b.status]));

    if (b.status === "pending") {
      const left = Math.max(0, Math.round((new Date(b.expires_at) - Date.now()) / 60000));
      actions.append(ui.el("span", "result-meta", `Seats held for ${left} more min`));
      const pay = ui.el("a", "btn-black btn-sm", b.payment_status === "pending" ? "Check payment" : "Pay now");
      pay.href = `/payment.html?booking=${b.booking_id}`;
      actions.append(pay);
      if (b.payment_status !== "pending") actions.append(cancelButton(b, li));
    }
    if (b.status === "confirmed") {
      const show = ui.el("a", "btn-black btn-sm", "Show ticket");
      show.href = `/ticket.html?booking=${b.booking_id}`;
      actions.append(show);
    }
    if (b.status === "confirmed" && new Date(b.cancel_until) > new Date()) {
      actions.append(cancelButton(b, li));
      const refund = b.pay_driver ? "" : " You get your money back.";
      actions.append(ui.el("span", "cancel-note", `Free to cancel until ${ui.when(b.cancel_until)}.${refund}`));
    }
    if (b.refund_status === "due") {
      actions.append(ui.el("span", "cancel-note",
        `Your refund of ${ui.money(b.total_price)} is being sent to your MoMo number.`));
    } else if (b.refund_status === "refunded") {
      actions.append(ui.el("span", "cancel-note", `${ui.money(b.total_price)} was refunded to your MoMo number.`));
    }
    li.append(actions);

    if (canRate(b)) li.append(rateForm(b, li));
    else if (b.rating) li.append(ui.el("p", "result-meta rated", `You rated this driver ${b.rating.score}/5.`));
    return li;
  }

  function ticket(b) {
    const dl = ui.el("dl", "ticket");
    [
      ["Booking number", `#${b.booking_id}`],
      ["Departure", ui.when(b.departure_time)],
      ["With", b.operator],
      b.booking_type === "bus"
        ? [b.seat_numbers.length > 1 ? "Seats" : "Seat", b.seat_numbers.join(", ")]
        : ["Seats", String(b.seats_booked)],
      [b.pay_driver ? "Pay the driver" : "Paid", ui.money(b.total_price)],
    ].forEach(([k, v]) => {
      const div = ui.el("div");
      div.append(ui.el("dt", null, k), ui.el("dd", null, v));
      dl.append(div);
    });
    return dl;
  }

  // Two steps, so a booking is never cancelled by one stray tap.
  function cancelButton(b, li) {
    const box = ui.el("span", "result-actions");
    const ask = ui.el("button", "btn-gray btn-sm", "Cancel booking");
    const yes = ui.el("button", "btn-black btn-sm", "Yes, cancel it");
    const no = ui.el("button", "btn-gray btn-sm", "Keep it");
    [ask, yes, no].forEach((x) => { x.type = "button"; });
    yes.hidden = no.hidden = true;
    const toggle = (asking) => { ask.hidden = asking; yes.hidden = no.hidden = !asking; };
    ask.addEventListener("click", () => toggle(true));
    no.addEventListener("click", () => toggle(false));
    yes.addEventListener("click", async () => {
      try {
        const { booking } = await ui.busy(yes, "Cancelling…", () =>
          api.post(`/bookings/${b.booking_id}/cancel`),
        );
        li.replaceWith(row(booking));
        ui.say(msg, booking.refund_status === "due"
          ? `Booking cancelled. Your ${ui.money(booking.total_price)} will be refunded to your MoMo number.`
          : "Booking cancelled. The seats are free for others again.", "info");
      } catch (err) {
        toggle(false);
        ui.say(msg, err.message);
      }
    });
    box.append(ask, yes, no);
    return box;
  }

  // Rides (not buses) can be rated once, after they have left.
  function canRate(b) {
    return b.status === "confirmed" && b.booking_type !== "bus" && !b.rating
      && new Date(b.departure_time) <= new Date();
  }

  function rateForm(b, li) {
    const form = ui.el("form", "form rate-form");
    form.noValidate = true;
    form.innerHTML = `
      <p class="rate-title">How was your ride with ${escapeHtml(b.operator)}?</p>
      <div class="modes" role="radiogroup" aria-label="Rating out of 5">
        ${[1, 2, 3, 4, 5].map((n) => `
          <label class="mode"><input type="radio" name="score" value="${n}"><span>${n}</span></label>`).join("")}
      </div>
      <label class="field">
        <span>Comment (optional)</span>
        <input type="text" name="comment" maxlength="500">
      </label>
      <button class="btn-black btn-sm" type="submit">Send rating</button>`;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const score = Number(form.elements.score.value);
      if (!score) {
        ui.say(msg, "Choose a score from 1 to 5.");
        return;
      }
      try {
        await ui.busy(form.querySelector("button"), "Sending…", () =>
          api.post("/ratings", {
            booking_id: b.booking_id,
            score,
            comment: form.elements.comment.value || undefined,
          }),
        );
        li.replaceWith(row({ ...b, rating: { score } }));
        ui.say(msg, "Thanks for rating your driver.", "info");
      } catch (err) {
        ui.say(msg, err.message);
      }
    });
    return form;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
})();
