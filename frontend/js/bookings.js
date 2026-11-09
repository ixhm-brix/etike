// The logged-in passenger's bookings, with cancel buttons.
(async function bookings() {
  if (!auth.require()) return;
  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");

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
    const status = ui.el("span", `status status-${b.status}`, b.status === "cancelled" ? "Cancelled" : "Booked");
    const type = { bus: "Bus", shared: "Shared seat", private: "Private car" }[b.booking_type];
    li.append(
      ui.el("span", "result-time", `${b.origin} to ${b.destination}`),
      ui.el("span", "result-price", ui.money(b.total_price)),
      ui.el("span", "result-meta", `${ui.when(b.departure_time)} · ${type} · ${b.operator}`),
      ui.el("span", "result-note", `${b.seats_booked} seat${b.seats_booked > 1 ? "s" : ""}`),
    );
    const actions = ui.el("div", "result-actions");
    actions.append(status);
    if (b.status === "confirmed") {
      const cancel = ui.el("button", "btn-gray btn-sm", "Cancel booking");
      cancel.type = "button";
      cancel.addEventListener("click", async () => {
        try {
          const { booking } = await ui.busy(cancel, "Cancelling…", () =>
            api.post(`/bookings/${b.booking_id}/cancel`),
          );
          li.replaceWith(row(booking));
          ui.say(msg, "Booking cancelled. The seats are free for others again.", "info");
        } catch (err) {
          ui.say(msg, err.message);
        }
      });
      actions.append(cancel);
    }
    li.append(actions);
    return li;
  }
})();
