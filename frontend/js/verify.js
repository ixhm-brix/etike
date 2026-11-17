// What a scanner sees: is this ETIKE ticket valid right now?
(async function verify() {
  const token = new URLSearchParams(location.search).get("t") || "";
  const loading = document.getElementById("loading");
  const box = document.getElementById("verdict");
  try {
    const result = await api.get(`/tickets/verify?t=${encodeURIComponent(token)}`);
    loading.hidden = true;
    box.hidden = false;
    box.classList.add(result.valid ? "is-valid" : "is-invalid");
    document.getElementById("verdict-title").textContent = result.valid ? "Valid" : "Not valid";
    document.getElementById("verdict-reason").textContent = result.reason;
    const t = result.ticket;
    if (!t) return;
    const TYPE = { bus: "Bus", shared: "Shared seat", private: "Private car" };
    const dl = document.getElementById("details");
    dl.hidden = false;
    [
      ["Booking", `#${t.booking_id}`],
      ["Passenger", t.passenger],
      ["Trip", `${t.origin} to ${t.destination}`],
      ["Departure", ui.when(t.departure_time)],
      [t.type === "bus" ? "Bus company" : "Driver", t.operator],
      ["Type", TYPE[t.type]],
      t.type === "bus"
        ? [t.seat_numbers.length > 1 ? "Seats" : "Seat", t.seat_numbers.join(", ")]
        : ["Seats", String(t.seat_numbers.length)],
    ].forEach(([k, v]) => {
      const div = ui.el("div");
      div.append(ui.el("dt", null, k), ui.el("dd", null, v));
      dl.append(div);
    });
  } catch (err) {
    loading.hidden = true;
    box.hidden = false;
    box.classList.add("is-invalid");
    document.getElementById("verdict-title").textContent = "Couldn't check";
    document.getElementById("verdict-reason").textContent = err.message;
  }
})();
