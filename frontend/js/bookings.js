// The logged-in passenger's bookings. Rides, like a taxi app: booked, then
// "on the way" when the driver starts, then pay with MoMo when the driver
// ends the ride. The page checks for changes while a ride is coming up or
// under way. Bus tickets (future phase): pay, show the ticket, refunds.
// Both: cancel until the cut-off before departure, rate the driver.
(async function bookings() {
  if (!auth.require()) return;
  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");

  const TYPE = { bus: "Bus", shared: "Shared seat", private: "Private car" };
  const STATUS = { pending: "Waiting for payment", confirmed: "Confirmed", cancelled: "Cancelled" };

  const justBooked = new URLSearchParams(location.search).get("new");
  let shown = []; // what the page shows now, to notice changes
  let unread = {}; // new messages per booking, for the Message buttons

  try {
    const [{ bookings: items }, counts] = await Promise.all([
      api.get("/bookings/mine"), api.get("/messages/unread").catch(() => ({ by_booking: {} })),
    ]);
    unread = counts.by_booking;
    loading.hidden = true;
    const fresh = items.find((b) => String(b.booking_id) === justBooked && b.status === "confirmed");
    if (fresh) {
      ui.toast("Your ride is booked",
        `${fresh.operator}, ${ui.when(fresh.departure_time)}. You pay ${ui.money(fresh.total_price)} `
        + "with MTN MoMo after the ride.");
      // So a reload doesn't show the banner again.
      history.replaceState(null, "", location.pathname);
    }
    if (!items.length) {
      list.replaceWith(ui.empty("No bookings yet", "When you book a trip it shows here.", {
        href: "/#trip", text: "Find a trip",
      }));
      return;
    }
    render(items);
    if (fresh) list.querySelector(`[data-booking="${fresh.booking_id}"]`)?.classList.add("is-new");
    setInterval(refresh, 15000);
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.message);
  }

  function render(items) {
    shown = items;
    list.replaceChildren(...items.map(row));
  }

  // While a ride is coming up or under way, check every 15 seconds so the
  // passenger sees "on the way" and then "pay now" without reloading.
  async function refresh() {
    const watching = shown.some((b) => b.pay_after_ride && b.status === "confirmed"
      && (b.ride_progress !== "ended" || b.payment_status === "pending" || b.driver_phone));
    if (!watching || document.hidden) return;
    try {
      const [{ bookings: items }, counts] = await Promise.all([
        api.get("/bookings/mine"), api.get("/messages/unread").catch(() => ({ by_booking: unread })),
      ]);
      const newMessages = JSON.stringify(counts.by_booking) !== JSON.stringify(unread);
      unread = counts.by_booking;
      const before = Object.fromEntries(shown.map((b) => [b.booking_id, b]));
      const changed = newMessages || items.some((b) => {
        const old = before[b.booking_id];
        return !old || old.ride_progress !== b.ride_progress || old.payment_status !== b.payment_status;
      });
      if (!changed) return;
      const ended = items.find((b) => b.can_pay && before[b.booking_id]?.ride_progress === "in_progress");
      const started = items.find((b) => b.ride_progress === "in_progress"
        && before[b.booking_id]?.ride_progress === "scheduled");
      if (ended) ui.toast("Your ride has ended", `Please pay ${ui.money(ended.total_price)} with MTN MoMo.`);
      else if (started) ui.toast("Your ride has started", `${started.operator} is on the way. Enjoy the trip!`);
      render(items);
    } catch (err) {
      // Try again on the next round.
    }
  }

  // What a ride booking's badge says.
  function rideStatus(b) {
    if (b.status !== "confirmed") return STATUS[b.status];
    if (b.payment_status === "success") return "Paid";
    return { scheduled: "Booked", in_progress: "On the way", ended: "Ride ended" }[b.ride_progress];
  }

  function row(b) {
    const li = ui.el("li", "result");
    li.dataset.booking = b.booking_id;
    li.append(
      ui.el("span", "result-time", `${b.origin} to ${b.destination}`),
      ui.el("span", "result-price", ui.money(b.total_price)),
      ui.el("span", "result-meta", `${ui.when(b.departure_time)} · ${TYPE[b.booking_type]} · ${b.operator}`),
      ui.el("span", "result-note", `${b.seats_booked} seat${b.seats_booked > 1 ? "s" : ""}`),
    );

    if (b.status === "confirmed") li.append(ticket(b));
    // Ride: where to meet and how to reach the driver (Call / WhatsApp
    // until a day after the ride; the chat stays readable).
    if (b.pay_after_ride && b.status === "confirmed") {
      li.append(ui.contact({ phone: b.driver_phone, bookingId: b.booking_id,
        unread: unread[b.booking_id] || 0, name: b.operator }));
    }

    const actions = ui.el("div", "result-actions");
    if (b.pay_after_ride) {
      const paid = b.payment_status === "success";
      actions.append(ui.el("span", `status status-${paid ? "confirmed" : b.status}`, rideStatus(b)));
      if (b.can_pay) {
        const pay = ui.el("a", "btn-black btn-sm", `Pay ${ui.money(b.total_price)} with MoMo`);
        pay.href = `/payment.html?booking=${b.booking_id}`;
        actions.append(pay);
        actions.append(ui.el("span", "cancel-note", b.payment_status === "failed"
          ? "The last payment didn't go through. Please try again."
          : "The ride has ended. Please pay the driver's fare with MTN MoMo."));
      } else if (b.status === "confirmed" && b.payment_status === "pending") {
        const check = ui.el("a", "btn-gray btn-sm", "Check payment");
        check.href = `/payment.html?booking=${b.booking_id}`;
        actions.append(check);
      } else if (b.status === "confirmed" && b.ride_progress === "in_progress") {
        actions.append(ui.el("span", "cancel-note", "Your driver has started the ride. You pay when it ends."));
      }
      if (b.status === "confirmed" && b.ride_progress !== "scheduled") {
        const map = ui.el("a", "btn-gray btn-sm",
          b.ride_progress === "in_progress" ? "Follow on the map" : "See the trip on the map");
        map.href = `/trip.html?ride=${b.offer_id}`;
        actions.append(map);
      }
    } else {
      actions.append(ui.el("span", `status status-${b.status}`, STATUS[b.status]));
    }

    if (b.status === "pending") {
      const left = Math.max(0, Math.round((new Date(b.expires_at) - Date.now()) / 60000));
      actions.append(ui.el("span", "result-meta", `Seats held for ${left} more min`));
      const pay = ui.el("a", "btn-black btn-sm", b.payment_status === "pending" ? "Check payment" : "Pay now");
      pay.href = `/payment.html?booking=${b.booking_id}`;
      actions.append(pay);
      if (b.payment_status !== "pending") actions.append(cancelButton(b, li));
    }
    if (b.status === "confirmed" && !b.pay_after_ride) {
      // Bus tickets only: a ride needs no ticket, like a taxi app.
      const show = ui.el("a", "btn-black btn-sm", "Show ticket");
      show.href = `/ticket.html?booking=${b.booking_id}`;
      actions.append(show);
    }
    if (b.status === "confirmed" && new Date(b.cancel_until) > new Date()
        && b.ride_progress !== "in_progress" && b.ride_progress !== "ended") {
      actions.append(cancelButton(b, li));
      const refund = b.pay_after_ride ? "" : " You get your money back.";
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
      ...(b.pickup_point ? [["Meet at", b.pickup_point]] : []),
      b.booking_type === "bus"
        ? [b.seat_numbers.length > 1 ? "Seats" : "Seat", b.seat_numbers.join(", ")]
        : ["Seats", String(b.seats_booked)],
      b.pay_after_ride && b.payment_status !== "success"
        ? ["Pay after the ride (MoMo)", ui.money(b.total_price)]
        : ["Paid", ui.money(b.total_price)],
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
