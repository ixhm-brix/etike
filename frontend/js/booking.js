// Confirm a booking. Bus: choose seats on the seat map. Shared ride: say
// how many seats. Private ride: the whole car. The server works out the price.
(async function booking() {
  const user = auth.require("passenger");
  if (!user) return;

  const params = new URLSearchParams(location.search);
  const tripId = params.get("trip");
  const offerId = params.get("offer");
  const form = document.getElementById("book");
  const msg = document.getElementById("msg");
  const loading = document.getElementById("loading");
  const button = form.querySelector('button[type="submit"]');
  const mapBox = document.getElementById("seatmap");
  const mapNote = document.getElementById("seatmap-note");
  const MAX_SEATS = 10;

  if (tripId && !(await api.features()).bus_booking) {
    loading.hidden = true;
    form.hidden = false;
    form.replaceChildren(msg);
    ui.say(msg, "Bus booking is not available yet. You can book a shared seat or a private car instead.");
    return;
  }

  let item;
  let seats;
  try {
    const base = tripId ? `/trips/${encodeURIComponent(tripId)}` : `/rides/${encodeURIComponent(offerId)}`;
    // Only buses have a seat map.
    const [detail, seatData] = await Promise.all([
      api.get(base), tripId ? api.get(`${base}/seats`) : null,
    ]);
    item = tripId ? detail.trip : detail.ride;
    seats = seatData;
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
  const unit = tripId ? item.price_rwf : item.price;
  const taken = new Set(seats ? seats.taken : []);
  const chosen = new Set();
  const seatsField = document.getElementById("seats-field");
  const seatsSelect = form.elements.seats;
  const left = tripId ? item.available_seats : item.seats_available;

  document.getElementById("subtitle").textContent =
    `${item.origin} to ${item.destination}, ${ui.when(item.departure_time)}`;
  if (!tripId) showPhotos(item.vehicle);

  // Buses are paid now; rides are paid to the driver.
  const note = document.getElementById("pay-note");
  if (tripId) {
    button.textContent = "Continue to payment";
    note.textContent = "You pay now with MTN MoMo. Your seats are held for 15 minutes while you pay.";
  } else {
    note.textContent = "Nothing to pay now. You pay the driver during or after the ride, in cash or by MoMo.";
  }

  if (tripId) {
    document.getElementById("seatmap-box").hidden = false;
    drawMap();
  } else if (!isPrivate) {
    // Shared ride: just how many seats; the driver shows you where to sit.
    seatsField.hidden = false;
    for (let i = 1; i <= Math.min(left, MAX_SEATS); i++) seatsSelect.append(new Option(String(i), String(i)));
    seatsSelect.value = String(Math.min(Number(params.get("seats")) || 1, Math.max(left, 1)));
    seatsSelect.addEventListener("change", updateSummary);
  }
  updateSummary();
  if (left < 1) {
    button.disabled = true;
    ui.say(msg, "This trip is full. Choose another one.");
  }

  function drawMap() {
    mapBox.replaceChildren();
    mapBox.classList.add("is-bus");
    seats.rows.forEach((row) => {
      const line = ui.el("div", "seat-row");
      row.forEach((cell) => {
        if (cell === "driver") {
          const d = ui.el("span", "seat is-driver", "Driver");
          d.setAttribute("aria-hidden", "true");
          line.append(d);
        } else if (cell === null) {
          line.append(ui.el("span", "seat-gap"));
        } else {
          line.append(seatButton(cell));
        }
      });
      mapBox.append(line);
    });
    mapNote.textContent = "Front of the bus at the top. The layout is a guide; seat numbers on the bus may differ slightly.";
  }

  function seatButton(n) {
    const b = ui.el("button", "seat", String(n));
    b.type = "button";
    const isTaken = taken.has(n);
    b.disabled = isTaken;
    b.classList.toggle("is-taken", isTaken);
    b.classList.toggle("is-chosen", chosen.has(n));
    b.setAttribute("aria-pressed", String(chosen.has(n)));
    b.setAttribute("aria-label", `Seat ${n}${isTaken ? ", taken" : chosen.has(n) ? ", yours" : ""}`);
    b.addEventListener("click", () => {
      if (chosen.has(n)) chosen.delete(n);
      else if (chosen.size >= MAX_SEATS) return ui.say(msg, `You can book up to ${MAX_SEATS} seats at once.`);
      else chosen.add(n);
      msg.textContent = "";
      drawMap();
      updateSummary();
      mapBox.querySelector(`[aria-label^="Seat ${n}"]`)?.focus();
    });
    return b;
  }

  function updateSummary() {
    const rows = [
      ["With", tripId ? item.company.name : `${item.driver_name}, ${item.vehicle.model}`],
      ["Type", tripId ? "Bus" : isPrivate ? "Private car (whole car)" : "Shared seat"],
      [isPrivate ? "Price for the car" : "Price per seat", ui.money(unit)],
    ];
    let count = 1;
    if (tripId) {
      const list = [...chosen].sort((a, b) => a - b);
      count = list.length;
      rows.push(["Seats", count ? list.join(", ") : "None chosen yet"]);
    } else if (isPrivate) {
      rows.push(["Seats", `All ${item.seats_available}`]);
    } else {
      count = Number(seatsSelect.value) || 1;
    }
    if (!isPrivate && count) rows.push(["Total", ui.money(unit * count)]);
    fill(document.getElementById("summary"), rows);
    button.disabled = left < 1 || (tripId && !count);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (tripId && !chosen.size) return ui.say(msg, "Choose at least one seat on the map.");
    const body = tripId ? { trip_id: Number(tripId) } : { offer_id: Number(offerId) };
    if (tripId) body.seat_numbers = [...chosen];
    else if (!isPrivate) body.seats = Number(seatsSelect.value);
    try {
      const { booking: b } = await ui.busy(button, "Booking…", () => api.post("/bookings", body));
      // A bus ticket is paid now; a ride is already confirmed.
      location.href = b.pay_driver
        ? `/bookings.html?new=${b.booking_id}`
        : `/payment.html?booking=${b.booking_id}`;
    } catch (err) {
      if (err.status === 401) return auth.require("passenger");
      if (err.status === 409 && tripId) {
        // Someone took a seat meanwhile: show the map as it is now.
        const fresh = await api.get(`/trips/${tripId}/seats`).catch(() => null);
        if (fresh) {
          seats = fresh;
          taken.clear();
          fresh.taken.forEach((n) => { taken.add(n); chosen.delete(n); });
          drawMap();
          updateSummary();
        }
      }
      ui.formError(form, msg, err);
    }
  });

  function showPhotos(vehicle) {
    const box = document.getElementById("photos");
    if (!vehicle.photos?.length) return;
    box.hidden = false;
    vehicle.photos.forEach((p, i) => {
      const img = ui.el("img");
      img.src = p.url;
      img.alt = `${vehicle.model}, photo ${i + 1}`;
      img.loading = "lazy";
      box.append(img);
    });
  }

  function fill(dl, pairs) {
    dl.replaceChildren();
    pairs.forEach(([k, v]) => {
      const row = ui.el("div", k === "Total" ? "summary-total" : null);
      row.append(ui.el("dt", null, k), ui.el("dd", null, v));
      dl.append(row);
    });
  }
})();
