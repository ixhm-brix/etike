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

  const docList = document.getElementById("documents");
  const docMsg = document.getElementById("documents-msg");
  const detailsForm = document.getElementById("details");
  const detailsMsg = document.getElementById("details-msg");
  const DETAIL_FIELDS = ["national_id_number", "date_of_birth", "gender", "home_district",
    "home_sector", "license_number"];

  // Approval status comes from the server, not from what was saved at login.
  try {
    await ui.fillPlaces(detailsForm.elements.home_district, "Choose");
    showDocuments(await api.get("/drivers/documents"));
  } catch (err) {
    ui.say(docMsg, err.message);
  }

  // Personal details: editable until the account is approved.
  function showDetails(details, approved) {
    DETAIL_FIELDS.forEach((name) => {
      detailsForm.elements[name].value = details[name] || "";
      detailsForm.elements[name].disabled = approved;
    });
    detailsForm.querySelector("button").hidden = approved;
    if (approved) {
      document.getElementById("details-note").textContent =
        "Checked and approved. To change them, contact ETIKE.";
    }
  }

  detailsForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(detailsForm);
    const body = {};
    DETAIL_FIELDS.forEach((name) => { body[name] = detailsForm.elements[name].value; });
    try {
      showDocuments(await ui.busy(detailsForm.querySelector("button"), "Saving…", () =>
        api.put("/drivers/details", body)));
      ui.say(detailsMsg, "Details saved.", "info");
    } catch (err) {
      ui.formError(detailsForm, detailsMsg, err);
    }
  });

  // What passengers say about this driver (the same reviews they see).
  let reviewsShown = false;
  async function showMyReviews(driver) {
    if (reviewsShown || driver.status !== "approved") return;
    reviewsShown = true;
    try {
      const said = await api.get(`/drivers/${driver.driver_id}/ratings`);
      document.getElementById("my-reviews").replaceChildren(
        ui.reviews(said, { empty: "No reviews yet. After your first rides, passengers' reviews show here." }));
    } catch (err) {
      // Not essential on this page.
    }
  }

  function showDocuments({ documents, details, driver }) {
    showMyReviews(driver);
    showDetails(details, driver.status === "approved");
    const missing = documents.filter((d) => !d.uploaded || d.expired).length;
    const noDetails = DETAIL_FIELDS.some((name) => !details[name]);
    if (driver.status === "approved") {
      status.textContent = "Your driver account is approved. Rides you post show up in search.";
    } else if (driver.status === "rejected") {
      status.textContent = `We could not approve your account${driver.rejection_reason ? `: ${driver.rejection_reason}` : "."} Upload a corrected document below and we will check again.`;
    } else if (noDetails) {
      status.textContent = "Fill in your details below, then upload your documents. You can add your vehicle meanwhile.";
    } else if (missing) {
      status.textContent = `Your account is waiting for your documents: ${missing} of ${documents.length} still to upload. You can add your vehicle meanwhile.`;
    } else {
      status.textContent = "Thanks, all your documents are in. We are checking them; you can post rides once your account is approved.";
    }
    rideForm.querySelector("button").disabled = driver.status !== "approved";
    docList.replaceChildren(...documents.map(documentRow));
  }

  function documentRow(d) {
    const li = ui.el("li", "doc");
    li.append(ui.el("span", "doc-name", d.label));
    let state = "Not uploaded yet";
    if (d.uploaded) {
      state = `Uploaded ${ui.date(d.uploaded_at)}`;
      if (d.expires_on) state += `, valid until ${ui.date(d.expires_on)}`;
      if (d.expired) state = `Expired on ${ui.date(d.expires_on)}. Upload the new one.`;
    }
    li.append(ui.el("span", `doc-state${!d.uploaded || d.expired ? " is-bad" : ""}`, state));

    const actions = ui.el("div", "doc-actions");
    if (d.uploaded) {
      const view = ui.el("button", "btn-gray btn-sm", "View");
      view.type = "button";
      view.addEventListener("click", () => ui.openFile(`/drivers/documents/${d.type}/file`, view, docMsg));
      actions.append(view);
    }
    let expiry = null;
    if (d.needs_expiry) {
      expiry = ui.el("input");
      expiry.type = "date";
      expiry.min = new Date().toISOString().slice(0, 10);
      if (d.expires_on && !d.expired) expiry.value = d.expires_on;
      const dateLabel = ui.el("label", "doc-date", "Valid until ");
      dateLabel.append(expiry);
      actions.append(dateLabel);
    }
    const label = ui.el("label", "btn-black btn-sm file-label", d.uploaded ? "Replace" : "Upload");
    const input = ui.el("input");
    input.type = "file";
    input.accept = "image/jpeg,image/png,application/pdf";
    input.setAttribute("aria-label", `Upload ${d.label}`);
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      if (expiry && !expiry.value) {
        ui.say(docMsg, `Enter the date your ${d.label.split(" (")[0].toLowerCase()} is valid until, then choose the file again.`);
        input.value = "";
        expiry.focus();
        return;
      }
      ui.say(docMsg, "");
      label.firstChild.textContent = "Uploading…";
      try {
        const extra = expiry ? { expires_on: expiry.value } : {};
        showDocuments(await api.upload(`/drivers/documents/${d.type}`, "document", file, extra));
        ui.say(docMsg, `${d.label.split(" (")[0]} uploaded.`, "info");
      } catch (err) {
        ui.say(docMsg, err.message);
        label.firstChild.textContent = d.uploaded ? "Replace" : "Upload";
        input.value = "";
      }
    });
    label.append(input);
    actions.append(label);
    li.append(actions);
    return li;
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
      ...vehicles.map(vehicleCard),
    );
    // Only finished cars (details and a photo) can carry passengers.
    f.vehicle_id.replaceChildren(
      new Option(vehicles.length ? "Choose a vehicle" : "Add a vehicle first", ""),
      ...vehicles.map((v) => {
        const o = new Option(`${v.plate_number}, ${v.colour || ""} ${v.model}${v.complete ? "" : " (finish it first)"}`.replace(/ +/g, " "), v.vehicle_id);
        o.disabled = !v.complete;
        return o;
      }),
    );
    const ready = vehicles.filter((v) => v.complete);
    if (ready.length === 1) f.vehicle_id.value = ready[0].vehicle_id;
    syncRide();
  }

  // A car with its photos: passengers see them on shared and private rides.
  function vehicleCard(v) {
    const li = ui.el("li", "result");
    li.append(ui.el("span", "result-time", `${v.colour || ""} ${v.model}`.trim()));
    li.append(ui.el("span", "result-meta result-wide", carFacts(v)));
    const missing = [];
    if (!v.colour || !v.year || v.has_ac === null || !v.luggage) missing.push("its details");
    if (!v.photos.length) missing.push("a photo");
    if (missing.length) {
      li.append(ui.el("span", "result-note result-wide is-bad",
        `Add ${missing.join(" and ")} to post rides with this car.`));
    }
    const editBtn = ui.el("button", "btn-gray btn-sm", "Edit details");
    editBtn.type = "button";
    editBtn.addEventListener("click", () => startEdit(v));
    li.append(editBtn);
    const photos = ui.el("div", "vehicle-photos");
    v.photos.forEach((p) => {
      const fig = ui.el("figure");
      const img = ui.el("img");
      img.src = p.url;
      img.alt = `${v.model}`;
      const remove = ui.el("button", "btn-gray btn-sm", "Remove");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        try {
          await ui.busy(remove, "…", () => api.del(`/drivers/vehicles/${v.vehicle_id}/photos/${p.photo_id}`));
          await loadVehicles();
        } catch (err) {
          ui.say(vehicleMsg, err.message);
        }
      });
      fig.append(img, remove);
      photos.append(fig);
    });
    if (v.photos.length < 3) {
      const label = ui.el("label", "btn-gray btn-sm file-label", v.photos.length ? "Add another photo" : "Add photos of your car");
      const input = ui.el("input");
      input.type = "file";
      input.accept = "image/jpeg,image/png,image/webp";
      input.addEventListener("change", async () => {
        const file = input.files[0];
        if (!file) return;
        try {
          label.firstChild.textContent = "Uploading…";
          await api.upload(`/drivers/vehicles/${v.vehicle_id}/photos`, "photo", file);
          ui.say(vehicleMsg, "Photo added. Passengers see it on your rides.", "info");
          await loadVehicles();
        } catch (err) {
          ui.say(vehicleMsg, err.message);
          label.firstChild.textContent = "Add photos of your car";
        }
      });
      label.append(input);
      photos.append(label);
    }
    li.append(photos);
    return li;
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

  // "Plate · 2019 · 4 passenger seats · Air conditioning · Medium luggage"
  function carFacts(v) {
    return [v.plate_number, v.year, `${v.seats} passenger seats`,
      v.has_ac === true ? "Air conditioning" : v.has_ac === false ? "No air conditioning" : null,
      v.luggage ? `${v.luggage[0].toUpperCase()}${v.luggage.slice(1)} luggage space` : null,
    ].filter(Boolean).join(" · ");
  }

  // The same form adds a car or corrects one (the plate can't change).
  let editing = null;
  const submitBtn = vehicleForm.querySelector('button[type="submit"]');
  const cancelBtn = document.getElementById("vehicle-cancel");
  function startEdit(v) {
    editing = v.vehicle_id;
    const e = vehicleForm.elements;
    e.plate_number.value = v.plate_number;
    e.plate_number.disabled = true;
    e.model.value = v.model;
    e.colour.value = v.colour || "";
    e.year.value = v.year || "";
    e.seats.value = v.seats;
    e.has_ac.value = v.has_ac === true ? "yes" : v.has_ac === false ? "no" : "";
    e.luggage.value = v.luggage || "";
    submitBtn.textContent = "Save changes";
    cancelBtn.hidden = false;
    vehicleForm.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function stopEdit() {
    editing = null;
    vehicleForm.reset();
    vehicleForm.elements.plate_number.disabled = false;
    submitBtn.textContent = "Add vehicle";
    cancelBtn.hidden = true;
  }
  cancelBtn.addEventListener("click", stopEdit);

  vehicleForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    ui.clearErrors(vehicleForm);
    const v = vehicleForm.elements;
    const body = {
      model: v.model.value,
      colour: v.colour.value,
      year: Number(v.year.value) || null,
      seats: Number(v.seats.value) || null,
      has_ac: v.has_ac.value === "yes" ? true : v.has_ac.value === "no" ? false : null,
      luggage: v.luggage.value,
    };
    try {
      if (editing) {
        await ui.busy(submitBtn, "Saving…", () => api.put(`/drivers/vehicles/${editing}`, body));
        ui.say(vehicleMsg, "Car details saved.", "info");
      } else {
        await ui.busy(submitBtn, "Adding…", () =>
          api.post("/drivers/vehicles", { ...body, plate_number: v.plate_number.value }));
        ui.say(vehicleMsg, "Car added. Now add at least one photo of it below.", "info");
      }
      stopEdit();
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
      pickup_point: f.pickup_point.value,
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
