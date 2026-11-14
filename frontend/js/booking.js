// Confirm a booking. The server works out the price; this page only shows
// the fare it sent and, after booking, the total it charged.
(async function booking() {
  const user = auth.require("passenger");
  if (!user) return;

  const params = new URLSearchParams(location.search);
  const tripId = params.get("trip");
  const offerId = params.get("offer");
  const form = document.getElementById("book");
  const msg = document.getElementById("msg");
  const loading = document.getElementById("loading");
  const seatsField = document.getElementById("seats-field");
  const seatsSelect = form.elements.seats;
  const button = form.querySelector("button");

  let item;
  try {
    item = tripId
      ? (await api.get(`/trips/${encodeURIComponent(tripId)}`)).trip
      : (await api.get(`/rides/${encodeURIComponent(offerId)}`)).ride;
  } catch (err) {
    loading.hidden = true;
    form.hidden = false;
    form.replaceChildren(msg);
    ui.say(msg, err.status === 404 ? "This trip no longer exists. Search again." : err.message);
    return;
  }
  loading.hidden = true;
  form.hidden = false;

  const isPrivate = item.ride_type === "private";
  const left = tripId ? item.available_seats : item.seats_available;
  const unit = tripId ? item.price_rwf : item.price;

  document.getElementById("subtitle").textContent =
    `${item.origin} to ${item.destination}, ${ui.when(item.departure_time)}`;

  const rows = [
    ["With", tripId ? item.company.name : `${item.driver_name}, ${item.vehicle.model}`],
    ["Type", tripId ? "Bus" : isPrivate ? "Private car (whole car)" : "Shared seat"],
    [isPrivate ? "Price for the car" : "Price per seat", ui.money(unit)],
  ];
  fill(document.getElementById("summary"), rows);

  if (isPrivate) {
    seatsField.hidden = true;
  } else {
    const max = Math.min(left, 10);
    for (let i = 1; i <= max; i++) seatsSelect.append(new Option(String(i), String(i)));
    seatsSelect.value = String(Math.min(Number(params.get("seats")) || 1, max));
  }
  if (left < 1) {
    button.disabled = true;
    ui.say(msg, "This trip is full. Choose another one.");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = tripId ? { trip_id: Number(tripId) } : { offer_id: Number(offerId) };
    if (!isPrivate) body.seats = Number(seatsSelect.value);
    try {
      const { booking: b } = await ui.busy(button, "Booking…", () => api.post("/bookings", body));
      // Seats are held now; pay to confirm them.
      location.href = `/payment.html?booking=${b.booking_id}`;
    } catch (err) {
      if (err.status === 401) return auth.require("passenger");
      ui.formError(form, msg, err);
    }
  });

  function fill(dl, pairs) {
    dl.replaceChildren();
    pairs.forEach(([k, v], i) => {
      const row = ui.el("div", i === pairs.length - 1 && dl.id === "receipt" ? "summary-total" : null);
      row.append(ui.el("dt", null, k), ui.el("dd", null, v));
      dl.append(row);
    });
  }
})();
