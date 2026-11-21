// The driver's trips, like a taxi app: Start ride when setting off, End ride
// on arrival; then each passenger pays with MTN MoMo and the payment shows
// up here (with a banner) while the page is open.
//
// With the driver's permission, the phone's location is recorded: where the
// ride started and ended, and every 30 seconds or so while it is on (the
// screen is kept awake for that). A web page can't track in the background,
// so this works while this page is open.
(async function driverTrips() {
  if (!auth.user() || auth.user().role !== "driver") return;
  const block = document.getElementById("trips-block");
  const list = document.getElementById("trips");
  const msg = document.getElementById("trips-msg");
  const DAY = 24 * 3600 * 1000;
  const SEND_EVERY = 30000; // ms between positions sent during a ride
  let rides = [];
  // Location sharing: "waiting" (not asked yet), "on" or "off" (refused or
  // unavailable), and when the last position was sent.
  let geo = { state: "waiting", lastSent: 0, watch: null, wakeLock: null };

  await load();
  setInterval(() => { if (!document.hidden && needsWatching()) load(true); }, 10000);

  async function load(quietly = false) {
    try {
      const fresh = (await api.get("/drivers/rides")).rides;
      if (quietly) {
        announcePayments(rides, fresh);
        announceMessages(rides, fresh);
      }
      rides = fresh;
      render();
      syncTracking();
    } catch (err) {
      if (!quietly) {
        block.hidden = false;
        ui.say(msg, err.message);
      }
    }
  }

  // What matters now: rides under way, ended but not fully paid, and the
  // ones leaving in the next day. Further ones are in "Post a ride" history.
  function current() {
    const soon = Date.now() + DAY;
    return rides.filter((r) => r.progress === "in_progress"
      || (r.progress === "ended" && r.paid < r.to_collect)
      || (r.progress === "ended" && Date.now() - new Date(r.ended_at) < DAY)
      || (r.progress === "scheduled" && new Date(r.departure_time) < soon && r.passengers.length));
  }

  // Keep checking while there are trips to follow: payments and messages.
  function needsWatching() {
    return current().length > 0;
  }

  function render() {
    const items = current();
    block.hidden = false;
    if (!items.length) {
      const next = rides.find((r) => r.progress === "scheduled" && r.passengers.length);
      list.replaceChildren(ui.el("li", "trip-empty", next
        ? `No trips in the next 24 hours. Next booked ride: ${next.origin} to ${next.destination}, ${ui.when(next.departure_time)}.`
        : "No booked trips yet. When passengers book your rides, they show here."));
      return;
    }
    list.replaceChildren(...items.map(card));
  }

  function card(r) {
    const li = ui.el("li", `trip trip-${r.progress}`);
    const head = ui.el("div", "trip-head");
    head.append(
      ui.el("strong", null, `${r.origin} to ${r.destination}`),
      ui.el("span", `status ${r.progress === "in_progress" ? "status-confirmed" : "status-pending"}`,
        { scheduled: "Not started", in_progress: "On the way", ended: "Ended" }[r.progress]),
    );
    li.append(head, ui.el("span", "trip-when",
      `${ui.when(r.departure_time)} · ${r.ride_type === "private" ? "Private car" : "Shared seats"}`));
    if (r.pickup_point) li.append(ui.el("span", "trip-when", `Meeting point: ${r.pickup_point}`));

    const people = ui.el("ul", "trip-people");
    r.passengers.forEach((p) => {
      const row = ui.el("li");
      const who = ui.el("div", "trip-person");
      who.append(ui.el("span", null, `${p.name} · ${p.seats} seat${p.seats > 1 ? "s" : ""}`),
        ui.contact({ phone: p.phone, bookingId: p.booking_id, unread: p.unread, name: p.name }));
      row.append(who);
      let state = ui.money(p.amount);
      let tone = "";
      if (r.progress === "ended") {
        if (p.payment_status === "success") { state = `Paid ${ui.money(p.amount)}`; tone = "is-paid"; }
        else if (p.payment_status === "pending") state = "Paying now…";
        else state = `Waiting for ${ui.money(p.amount)}`;
      }
      row.append(ui.el("span", `trip-pay ${tone}`, state));
      people.append(row);
    });
    li.append(people);

    if (r.progress === "ended") {
      li.append(ui.el("p", "trip-total",
        r.paid >= r.to_collect
          ? `All paid: ${ui.money(r.paid)}`
          : `Received ${ui.money(r.paid)} of ${ui.money(r.to_collect)}`));
    }
    if (r.progress === "in_progress") li.append(liveLine());
    if (r.progress !== "scheduled") {
      const see = ui.el("a", "trip-map-link", r.progress === "ended" ? "See the trip on the map" : "Follow the trip on the map");
      see.href = `/trip.html?ride=${r.offer_id}`;
      li.append(see);
    }
    if (r.progress === "scheduled") {
      // The server allows starting from one hour before departure.
      const from = new Date(new Date(r.departure_time).getTime() - 3600 * 1000);
      if (Date.now() >= from) li.append(action(r, "start", "Start ride"));
      else {
        const at = from.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
        li.append(ui.el("p", "trip-when", `You can start this ride from ${at}.`));
      }
    }
    if (r.progress === "in_progress") li.append(action(r, "end", "End ride"));
    return li;
  }

  function action(r, what, label) {
    const b = ui.el("button", "btn-black trip-action", label);
    b.type = "button";
    b.addEventListener("click", async () => {
      try {
        const { ride } = await ui.busy(b, what === "start" ? "Starting…" : "Ending…", async () => {
          // Where the car is now, if the driver allows it (the ride works without).
          const here = await position();
          return api.post(`/rides/${r.offer_id}/${what}`, here || {});
        });
        rides = rides.map((x) => (x.offer_id === ride.offer_id ? ride : x));
        render();
        syncTracking();
        if (what === "start") {
          ui.toast("Ride started", geo.state === "off"
            ? "Location is off, so this trip isn't recorded on the map. Tap End ride when you arrive."
            : "Have a safe trip. Keep this page open so the trip is recorded. Tap End ride when you arrive.");
        } else {
          ui.toast("Ride ended", `Your passengers can now pay ${ui.money(ride.to_collect)} with MTN MoMo.`);
        }
      } catch (err) {
        ui.say(msg, err.message);
      }
    });
    return b;
  }

  // ---- Location ----

  // One position now: {lat, lng, accuracy}, or null if it isn't shared.
  function position() {
    return new Promise((resolve) => {
      if (!navigator.geolocation) { geo.state = "off"; resolve(null); return; }
      navigator.geolocation.getCurrentPosition(
        (p) => { geo.state = "on"; resolve(toBody(p)); },
        () => { geo.state = "off"; resolve(null); },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
      );
    });
  }

  function toBody(p) {
    return { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: Math.round(p.coords.accuracy) };
  }

  // While a ride is on: follow the phone's position and send it every
  // SEND_EVERY ms, and keep the screen awake. Stop when no ride is on.
  function syncTracking() {
    const on = rides.filter((r) => r.progress === "in_progress");
    if (!on.length || !navigator.geolocation) {
      if (geo.watch !== null) navigator.geolocation.clearWatch(geo.watch);
      geo.watch = null;
      geo.wakeLock?.release().catch(() => {});
      geo.wakeLock = null;
      return;
    }
    keepAwake();
    if (geo.watch !== null) return;
    geo.watch = navigator.geolocation.watchPosition(async (p) => {
      geo.state = "on";
      if (Date.now() - geo.lastSent < SEND_EVERY) return;
      geo.lastSent = Date.now();
      const body = toBody(p);
      await Promise.all(rides.filter((r) => r.progress === "in_progress").map((r) =>
        api.post(`/rides/${r.offer_id}/locations`, body).catch(() => null)));
      updateLiveLines();
    }, () => {
      geo.state = "off";
      updateLiveLines();
    }, { enableHighAccuracy: true, maximumAge: 15000, timeout: 60000 });
  }

  async function keepAwake() {
    if (geo.wakeLock || !navigator.wakeLock || document.hidden) return;
    try {
      geo.wakeLock = await navigator.wakeLock.request("screen");
      geo.wakeLock.addEventListener("release", () => { geo.wakeLock = null; });
    } catch (err) {
      // Not allowed (e.g. battery saver): tracking still works while the screen is on.
    }
  }
  // The screen lock is dropped when the page is hidden; take it back.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && rides.some((r) => r.progress === "in_progress")) keepAwake();
  });

  function liveLine() {
    const p = ui.el("p", "trip-live");
    p.dataset.live = "1";
    fillLive(p);
    return p;
  }

  function fillLive(p) {
    p.classList.toggle("is-off", geo.state === "off");
    p.textContent = geo.state === "off"
      ? "Location off: allow location for ETIKE to record this trip."
      : geo.lastSent
        ? `Sharing your location · last sent ${new Date(geo.lastSent).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`
        : "Sharing your location. Keep this page open during the ride.";
  }

  function updateLiveLines() {
    document.querySelectorAll("[data-live]").forEach(fillLive);
  }

  // A banner when a passenger writes.
  function announceMessages(before, after) {
    const old = new Map();
    before.forEach((r) => r.passengers.forEach((p) => old.set(p.booking_id, p.unread)));
    after.forEach((r) => r.passengers.forEach((p) => {
      if (p.unread > (old.get(p.booking_id) || 0)) {
        ui.toast(`New message from ${p.name}`, "Tap Message to read and reply.");
      }
    }));
  }

  // A banner for every payment that came in since the last check.
  function announcePayments(before, after) {
    const old = new Map();
    before.forEach((r) => r.passengers.forEach((p) => old.set(p.booking_id, p.payment_status)));
    after.forEach((r) => r.passengers.forEach((p) => {
      if (p.payment_status === "success" && old.get(p.booking_id) !== "success") {
        ui.toast("Payment received", `${p.name} paid ${ui.money(p.amount)} for ${r.origin} to ${r.destination}.`, "good");
      }
    }));
  }
})();
