// Search results: ride offers (and bus trips, when that future phase is
// switched on) from the API, never made up.
(async function results() {
  // Prices are for members. Not logged in: log in, then come back here.
  if (!auth.require()) return;
  const params = new URLSearchParams(location.search);
  const origin = params.get("origin");
  const destination = params.get("destination");
  const date = params.get("date") || "";
  const busOn = (await api.features()).bus_booking;
  const types = busOn ? ["bus", "shared", "private"] : ["shared", "private"];
  const type = types.includes(params.get("type")) ? params.get("type") : "shared";
  const seats = params.get("seats") || "1";

  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");

  if (!origin || !destination) {
    location.replace("/#trip");
    return;
  }
  document.title = `${origin} to ${destination} – ETIKE`;
  document.getElementById("title").textContent = `${origin} to ${destination}`;
  const change = ui.el("a", null, "Change search");
  change.href = `/?${params}#trip`;
  document.getElementById("subtitle").append(date ? `${ui.day(date)}. ` : "Any day. ", change);

  // Tabs to switch between bus, shared seat and private car.
  const tabs = document.getElementById("tabs");
  [["bus", "Bus"], ["shared", "Shared seat"], ["private", "Private car"]]
    .filter(([value]) => types.includes(value))
    .forEach(([value, label]) => {
    const a = ui.el("a", "mode");
    const p = new URLSearchParams(params);
    p.set("type", value);
    a.href = `?${p}`;
    if (value === type) a.setAttribute("aria-current", "page");
    a.append(ui.el("span", null, label));
    tabs.append(a);
  });

  const query = new URLSearchParams({ origin, destination });
  if (date) query.set("date", date);

  try {
    let items;
    if (type === "bus") {
      items = (await api.get(`/trips?${query}`)).trips.map(busCard);
    } else {
      query.set("type", type);
      items = (await api.get(`/rides?${query}`)).rides.map(rideCard);
    }
    loading.hidden = true;
    if (!items.length) {
      const what = { bus: "bus trips", shared: "shared seats", private: "private cars" }[type];
      const box = ui.empty(
        date ? `No ${what} on ${ui.day(date)}` : `No ${what} found for this route yet`,
        "Try another day or another way to travel.",
        { href: `/?${params}#trip`, text: "Change search" },
      );
      list.replaceWith(box);
      if (date) box.append(await otherDays(what));
      return;
    }
    list.append(...items);
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.message);
  }

  // Nothing on the chosen day: offer the next days that do have some, so
  // people don't give up on a route that runs tomorrow.
  async function otherDays(what) {
    const any = new URLSearchParams({ origin, destination });
    if (type !== "bus") any.set("type", type);
    try {
      const found = type === "bus"
        ? (await api.get(`/trips?${any}`)).trips
        : (await api.get(`/rides?${any}`)).rides;
      const days = [...new Set(found.map((x) => x.departure_time.slice(0, 10)))]
        .filter((d) => d !== date).sort().slice(0, 3);
      const box = ui.el("div", "other-days");
      if (!days.length) return box;
      box.append(ui.el("span", null, `Next days with ${what}:`));
      days.forEach((d) => {
        const p = new URLSearchParams(params);
        p.set("date", d);
        const a = ui.el("a", "btn-gray btn-sm", ui.day(d));
        a.href = `?${p}`;
        box.append(a);
      });
      return box;
    } catch (err) {
      return ui.el("span"); // the empty message above is enough
    }
  }

  function card({ time, price, meta, note, href, photo }) {
    const li = ui.el("li", "result");
    if (photo) {
      li.classList.add("has-photo");
      const img = ui.el("img", "result-photo");
      img.src = photo.url;
      img.alt = "";
      img.loading = "lazy";
      li.append(img);
    }
    li.append(
      ui.el("span", "result-time", time),
      ui.el("span", "result-price", price),
      ui.el("span", "result-meta", meta),
      ui.el("span", "result-note", note),
    );
    const actions = ui.el("div", "result-actions");
    const book = ui.el("a", "btn-black btn-sm", "Choose");
    book.href = href;
    actions.append(book);
    li.append(actions);
    return li;
  }

  function busCard(t) {
    return card({
      time: ui.when(t.departure_time),
      price: ui.money(t.price_rwf),
      meta: t.company.name,
      note: `per seat · ${t.available_seats} left`,
      href: `/booking.html?trip=${t.trip_id}&seats=${seats}`,
    });
  }

  function rideCard(r) {
    const isPrivate = r.ride_type === "private";
    return card({
      time: ui.when(r.departure_time),
      price: ui.money(r.price),
      meta: `${r.driver_name}${r.driver_rating ? ` ★ ${r.driver_rating.toFixed(1)}` : ""} · `
        + `${[r.vehicle.colour, r.vehicle.model].filter(Boolean).join(" ")}${r.vehicle.year ? `, ${r.vehicle.year}` : ""}`
        + `${r.vehicle.has_ac ? " · AC" : ""}`,
      note: isPrivate
        ? `whole car · ${r.vehicle.seats} passenger seats`
        : `per seat · ${r.seats_available} left`,
      href: `/booking.html?offer=${r.offer_id}&seats=${seats}`,
      photo: r.vehicle.photos?.[0],
    });
  }
})();
