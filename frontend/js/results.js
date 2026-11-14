// Search results: bus trips or ride offers from the API, never made up.
(async function results() {
  const params = new URLSearchParams(location.search);
  const origin = params.get("origin");
  const destination = params.get("destination");
  const date = params.get("date") || "";
  const type = ["bus", "shared", "private"].includes(params.get("type")) ? params.get("type") : "bus";
  const seats = params.get("seats") || "1";

  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");

  if (!origin || !destination) {
    location.replace("/search.html");
    return;
  }
  document.title = `${origin} to ${destination} – ETIKE`;
  document.getElementById("title").textContent = `${origin} to ${destination}`;
  const change = ui.el("a", null, "Change search");
  change.href = `/search.html?${params}`;
  document.getElementById("subtitle").append(date ? `${ui.day(date)}. ` : "Any day. ", change);

  // Tabs to switch between bus, shared seat and private car.
  const tabs = document.getElementById("tabs");
  [["bus", "Bus"], ["shared", "Shared seat"], ["private", "Private car"]].forEach(([value, label]) => {
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
      list.replaceWith(
        ui.empty(`No ${what} found for this route yet`, "Try another day or another way to travel.", {
          href: `/search.html?${params}`,
          text: "Change search",
        }),
      );
      return;
    }
    list.append(...items);
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.message);
  }

  function card({ time, price, meta, note, href }) {
    const li = ui.el("li", "result");
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
      meta: `${r.driver_name}${r.driver_rating ? ` (${r.driver_rating}/5)` : ""} · ${r.vehicle.model}`,
      note: isPrivate ? `whole car · ${r.seats_available} seats` : `per seat · ${r.seats_available} left`,
      href: `/booking.html?offer=${r.offer_id}&seats=${seats}`,
    });
  }
})();
