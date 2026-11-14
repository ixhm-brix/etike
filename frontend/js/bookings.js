// The logged-in passenger's bookings: pay or cancel pending ones, see the
// ticket for confirmed ones, and rate the driver after a ride.
(async function bookings() {
  if (!auth.require()) return;
  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");

  const TYPE = { bus: "Bus", shared: "Shared seat", private: "Private car" };
  const STATUS = { pending: "Waiting for payment", confirmed: "Confirmed", cancelled: "Cancelled" };

  try {
    const { bookings: items } = await api.get("/bookings/mine");
    loading.hidden = true;
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
      ["Seats", String(b.seats_booked)],
      ["Paid", ui.money(b.total_price)],
    ].forEach(([k, v]) => {
      const div = ui.el("div");
      div.append(ui.el("dt", null, k), ui.el("dd", null, v));
      dl.append(div);
    });
    return dl;
  }

  function cancelButton(b, li) {
    const button = ui.el("button", "btn-gray btn-sm", "Cancel booking");
    button.type = "button";
    button.addEventListener("click", async () => {
      try {
        const { booking } = await ui.busy(button, "Cancelling…", () =>
          api.post(`/bookings/${b.booking_id}/cancel`),
        );
        li.replaceWith(row(booking));
        ui.say(msg, "Booking cancelled. The seats are free for others again.", "info");
      } catch (err) {
        ui.say(msg, err.message);
      }
    });
    return button;
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
