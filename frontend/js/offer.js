// Driver page: add vehicles and post shared or private rides.
(async function offer() {
  if (!auth.require("driver")) return;

  const status = document.getElementById("status");
  const vehicleList = document.getElementById("vehicles");
  const vehicleForm = document.getElementById("vehicle");
  const vehicleMsg = document.getElementById("vehicle-msg");
  const rideForm = document.getElementById("ride");
  const rideMsg = document.getElementById("ride-msg");
  const f = rideForm.elements;
  let vehicles = [];

  // Approval status comes from the server, not from what was saved at login.
  try {
    const { user } = await api.get("/auth/me");
    status.textContent = user.driver.is_approved
      ? "Your driver account is approved. Rides you post show up in search."
      : "Your driver account is waiting for approval. You can add your vehicle now, and post rides once we have checked your licence.";
    rideForm.querySelector("button").disabled = !user.driver.is_approved;
  } catch (err) {
    ui.say(rideMsg, err.message);
  }

  await Promise.all([
    ui.fillPlaces(f.origin, "Leaving from", "Kigali"),
    ui.fillPlaces(f.destination, "Going to"),
    loadVehicles(),
  ]).catch((err) => ui.say(rideMsg, err.message));

  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  f.departure_time.min = now.toISOString().slice(0, 16);

  async function loadVehicles() {
    vehicles = (await api.get("/drivers/vehicles")).vehicles;
    vehicleList.hidden = !vehicles.length;
    vehicleList.replaceChildren(
      ...vehicles.map((v) => {
        const li = ui.el("li", "result");
        li.append(ui.el("span", "result-meta", `${v.plate_number} · ${v.model} · ${v.seats} seats`));
        return li;
      }),
    );
    f.vehicle_id.replaceChildren(
      new Option(vehicles.length ? "Choose a vehicle" : "Add a vehicle first", ""),
      ...vehicles.map((v) => new Option(`${v.plate_number}, ${v.model}`, v.vehicle_id)),
    );
    if (vehicles.length === 1) f.vehicle_id.value = vehicles[0].vehicle_id;
    syncRide();
  }

  function syncRide() {
    const isPrivate = f.ride_type.value === "private";
    document.getElementById("price-label").textContent = isPrivate
      ? "Price for the whole car (RWF)"
      : "Price per seat (RWF)";
    // A private ride is the whole car, so the seat count is the vehicle's.
    document.getElementById("seats-field").hidden = isPrivate;
    const vehicle = vehicles.find((v) => String(v.vehicle_id) === f.vehicle_id.value);
    if (vehicle) {
      f.seats_available.max = vehicle.seats;
      if (!f.seats_available.value) f.seats_available.value = vehicle.seats;
    }
  }
  rideForm.addEventListener("change", syncRide);

  vehicleForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(vehicleForm);
    const v = vehicleForm.elements;
    try {
      await ui.busy(vehicleForm.querySelector("button"), "Adding…", () =>
        api.post("/drivers/vehicles", {
          plate_number: v.plate_number.value,
          model: v.model.value,
          seats: Number(v.seats.value) || null,
        }),
      );
      vehicleForm.reset();
      ui.say(vehicleMsg, "Vehicle added.", "info");
      await loadVehicles();
    } catch (err) {
      ui.formError(vehicleForm, vehicleMsg, err);
    }
  });

  rideForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(rideForm);
    const body = {
      vehicle_id: Number(f.vehicle_id.value) || null,
      origin: f.origin.value,
      destination: f.destination.value,
      ride_type: f.ride_type.value,
      departure_time: f.departure_time.value,
      price: Number(f.price.value) || null,
    };
    if (body.ride_type === "shared" && f.seats_available.value) {
      body.seats_available = Number(f.seats_available.value);
    }
    try {
      const { ride } = await ui.busy(rideForm.querySelector("button"), "Posting…", () =>
        api.post("/rides", body),
      );
      ui.say(
        rideMsg,
        `Posted: ${ride.origin} to ${ride.destination}, ${ui.when(ride.departure_time)}, ${ui.money(ride.price)}.`,
        "info",
      );
      rideForm.reset();
      syncRide();
    } catch (err) {
      ui.formError(rideForm, rideMsg, err);
    }
  });
})();
