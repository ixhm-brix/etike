// A confirmed booking's ticket, with a QR code to show at boarding.
(async function ticket() {
  if (!auth.require()) return;
  const id = new URLSearchParams(location.search).get("booking");
  const msg = document.getElementById("msg");
  const loading = document.getElementById("loading");

  try {
    const [data, svg] = await Promise.all([
      api.get(`/bookings/${encodeURIComponent(id)}/ticket`),
      qrSvg(id),
    ]);
    const b = data.booking;
    loading.hidden = true;
    document.getElementById("ticket").hidden = false;
    document.getElementById("route").textContent = `${b.origin} to ${b.destination}`;
    document.getElementById("booking-no").textContent = `#${b.booking_id}`;
    // The SVG comes from our own API, made by the QR library.
    document.getElementById("qr").innerHTML = svg;
    const TYPE = { bus: "Bus", shared: "Shared seat", private: "Private car" };
    const rows = [
      ["Passenger", data.passenger],
      ["Departure", ui.when(b.departure_time)],
      [b.booking_type === "bus" ? "Bus company" : "Driver", b.operator],
      ["Type", TYPE[b.booking_type]],
      b.booking_type === "bus"
        ? [b.seat_numbers.length > 1 ? "Seats" : "Seat", b.seat_numbers.join(", ")]
        : ["Seats", String(b.seats_booked)],
      ["Paid", ui.money(b.total_price)],
    ];
    const dl = document.getElementById("details");
    rows.forEach(([k, v]) => {
      const div = ui.el("div");
      div.append(ui.el("dt", null, k), ui.el("dd", null, v));
      dl.append(div);
    });
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.status === 404 ? "We couldn't find this ticket." : err.message);
  }

  // The QR image needs the login token, so fetch it rather than use <img src>.
  async function qrSvg(bookingId) {
    const res = await fetch(`/api/bookings/${encodeURIComponent(bookingId)}/ticket/qr`, {
      headers: { Authorization: `Bearer ${auth.token()}` },
    });
    if (!res.ok) throw new api.ApiError("We couldn't make the QR code.", res.status, null);
    const text = await res.text();
    // Keep only the <svg> element.
    return text.slice(text.indexOf("<svg"));
  }
})();
