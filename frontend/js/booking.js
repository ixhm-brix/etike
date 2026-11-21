// Confirm a booking. Ride: a full review first (car photos, driver and
// rating, the trip, the price, how you pay), then one Confirm button, like
// a taxi app. Bus: choose seats on the seat map. The server works out the
// price either way.
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

  // Buses are paid now; rides are paid with MoMo after the ride.
  const note = document.getElementById("pay-note");
  if (tripId) {
    button.textContent = "Continue to payment";
    note.textContent = "You pay now with MTN MoMo. Your seats are held for 15 minutes while you pay.";
  } else {
    document.getElementById("title").textContent = "Review your ride";
    document.getElementById("subtitle").textContent = "Check everything, then confirm.";
    document.getElementById("summary").hidden = true;
    await showReview();
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

  // The ride review: what a passenger checks before confirming.
  async function showReview() {
    const box = document.getElementById("review");
    box.hidden = false;
    const v = item.vehicle;

    // Car photos, swipeable, with a counter.
    if (v.photos?.length) {
      const gallery = ui.el("div", "gallery");
      const strip = ui.el("div", "gallery-strip");
      const count = ui.el("span", "gallery-count", `1 / ${v.photos.length}`);
      v.photos.forEach((p, i) => {
        const img = ui.el("img");
        img.src = p.url;
        img.alt = `${v.model}, photo ${i + 1} of ${v.photos.length}`;
        img.loading = i ? "lazy" : "eager";
        strip.append(img);
      });
      strip.addEventListener("scroll", () => {
        const i = Math.round(strip.scrollLeft / strip.clientWidth);
        count.textContent = `${i + 1} / ${v.photos.length}`;
      }, { passive: true });
      gallery.append(strip);
      if (v.photos.length > 1) gallery.append(count);
      box.append(gallery);
    }

    // Driver and car.
    const driver = ui.el("div", "review-card review-driver");
    const initials = item.driver_name.split(" ").map((w) => w[0]).slice(0, 2).join("");
    const who = ui.el("div");
    who.append(ui.el("strong", null, item.driver_name),
      ui.el("span", null, item.driver_rating ? `★ ${item.driver_rating.toFixed(1)} rating` : "New driver, no ratings yet"));
    const car = ui.el("div", "review-car");
    car.append(ui.el("strong", null, v.model), ui.el("span", null, `${v.seats} passenger seats`));
    driver.append(ui.el("span", "avatar", initials), who, car);
    box.append(driver);

    // The trip.
    const trip = ui.el("div", "review-card review-trip");
    const stops = ui.el("ol", "review-stops");
    stops.append(ui.el("li", "is-from", item.origin), ui.el("li", "is-to", item.destination));
    const when = ui.el("p", "review-when", `${ui.day(item.departure_time)} at ${ui.clock(item.departure_time)}`);
    const kind = ui.el("p", "review-kind", isPrivate ? "Private car: the whole car is yours" : "Shared seat: you share the car");
    trip.append(stops, when, kind);
    if (item.pickup_point) {
      const meet = ui.el("p", "review-meet");
      meet.append(ui.el("strong", null, "Meeting point"), ui.el("span", null, item.pickup_point));
      trip.append(meet);
    }
    box.append(trip);

    // How you pay, and until when you can cancel for free.
    const { cancel_cutoff_hours: hours = 2 } = await api.config();
    // Departure times are Rwanda local time ("2026-11-22T15:00"); keep the
    // deadline in the same form so it is shown the same way.
    const cut = new Date(new Date(item.departure_time).getTime() - hours * 3600 * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    const until = `${cut.getFullYear()}-${pad(cut.getMonth() + 1)}-${pad(cut.getDate())}T${pad(cut.getHours())}:${pad(cut.getMinutes())}`;
    const pay = ui.el("div", "review-card review-pay");
    pay.append(ui.el("strong", null, "Pay with MTN MoMo after the ride"),
      ui.el("span", null, "Nothing to pay now. When the driver ends the ride, you pay the total below with MTN MoMo in ETIKE."),
      ui.el("span", null, `Free cancellation until ${ui.day(until)} at ${ui.clock(until)}.`));
    box.append(pay);

    // Price: per seat (shared) or for the car (private), and the total.
    // Shared ride: how many seats, right above the price.
    box.append(document.getElementById("seats-field"));
    const price = ui.el("dl", "summary review-price");
    price.id = "review-price";
    box.append(price);
    note.hidden = true;
  }

  function updateSummary() {
    if (!tripId) {
      const count = isPrivate ? 1 : Number(seatsSelect.value) || 1;
      fill(document.getElementById("review-price"), [
        [isPrivate ? "Price for the whole car" : "Price per seat", ui.money(unit)],
        ...(isPrivate ? [] : [["Seats", String(count)]]),
        ["Total to pay after the ride", ui.money(unit * count)],
      ], "Total to pay after the ride");
      button.textContent = `Confirm booking · ${ui.money(unit * count)}`;
      button.disabled = left < 1;
      return;
    }
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
      // A bus ticket is paid now; a ride is booked and paid after the ride.
      location.href = b.pay_after_ride
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

  function fill(dl, pairs, totalLabel = "Total") {
    dl.replaceChildren();
    pairs.forEach(([k, v]) => {
      const row = ui.el("div", k === totalLabel ? "summary-total" : null);
      row.append(ui.el("dt", null, k), ui.el("dd", null, v));
      dl.append(row);
    });
  }
})();
