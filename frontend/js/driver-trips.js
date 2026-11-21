// The driver's trips, like a taxi app: Start ride when setting off, End ride
// on arrival; then each passenger pays with MTN MoMo and the payment shows
// up here (with a banner) while the page is open.
(async function driverTrips() {
  if (!auth.user() || auth.user().role !== "driver") return;
  const block = document.getElementById("trips-block");
  const list = document.getElementById("trips");
  const msg = document.getElementById("trips-msg");
  const DAY = 24 * 3600 * 1000;
  let rides = [];

  await load();
  setInterval(() => { if (!document.hidden && needsWatching()) load(true); }, 10000);

  async function load(quietly = false) {
    try {
      const fresh = (await api.get("/drivers/rides")).rides;
      if (quietly) announcePayments(rides, fresh);
      rides = fresh;
      render();
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

  function needsWatching() {
    return rides.some((r) => r.progress === "ended" && r.paid < r.to_collect);
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

    const people = ui.el("ul", "trip-people");
    r.passengers.forEach((p) => {
      const row = ui.el("li");
      row.append(ui.el("span", null, `${p.name} · ${p.seats} seat${p.seats > 1 ? "s" : ""}`));
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
        const { ride } = await ui.busy(b, what === "start" ? "Starting…" : "Ending…",
          () => api.post(`/rides/${r.offer_id}/${what}`));
        rides = rides.map((x) => (x.offer_id === ride.offer_id ? ride : x));
        render();
        if (what === "start") ui.toast("Ride started", "Have a safe trip. Tap End ride when you arrive.");
        else ui.toast("Ride ended", `Your passengers can now pay ${ui.money(ride.to_collect)} with MTN MoMo.`);
      } catch (err) {
        ui.say(msg, err.message);
      }
    });
    return b;
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
