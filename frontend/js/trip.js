// A ride's trip record on the map: where the driver's phone was from Start
// ride to End ride. While the ride is on, it refreshes so passengers can
// follow the car. Only the driver, the ride's passengers and admins can see it.
(async function trip() {
  if (!auth.require()) return;
  const rideId = new URLSearchParams(location.search).get("ride");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");
  const box = document.getElementById("trip");
  const map = RwandaMap.render(document.getElementById("map-canvas"));
  let timer = null;

  await load();

  async function load() {
    let data;
    try {
      data = await api.get(`/rides/${encodeURIComponent(rideId)}/track`);
    } catch (err) {
      loading.hidden = true;
      ui.say(msg, err.status === 404 ? "We couldn't find this trip." : err.message);
      return;
    }
    loading.hidden = true;
    show(data);
    const live = data.ride.progress === "in_progress";
    if (live && !timer) timer = setInterval(() => { if (!document.hidden) load(); }, 20000);
    if (!live && timer) clearInterval(timer);
  }

  function show({ ride, points, started_at: started, ended_at: ended, distance_km: km }) {
    const live = ride.progress === "in_progress";
    document.getElementById("title").textContent = live ? "Ride in progress" : "Trip on the map";
    document.getElementById("subtitle").textContent =
      `${ride.origin} to ${ride.destination} with ${ride.driver_name}, ${ui.when(ride.departure_time)}`;
    box.hidden = false;
    map.showTrack(points, { live });

    if (!started) ui.say(msg, "The driver hasn't started this ride yet.", "info");
    else if (!points.length) ui.say(msg, "No location was recorded for this ride: the driver didn't share it.", "info");
    else if (live) ui.say(msg, "The map follows the car while the driver's ETIKE page is open. It updates every 20 seconds.", "info");
    else msg.textContent = "";

    const first = points[0];
    const last = points[points.length - 1];
    const near = (p) => (p ? `, near ${RwandaMap.nearest(p.lat, p.lng)}` : "");
    const rows = [
      ["Started", started ? `${time(started)}${near(points.find((p) => p.kind === "start") || first)}` : "Not yet"],
      [live ? "Last seen" : "Ended", live
        ? (last ? `${time(last.at)}${near(last)}` : "No position yet")
        : ended ? `${time(ended)}${near(points.find((p) => p.kind === "end") || last)}` : "Not yet"],
    ];
    if (points.length > 1) rows.push(["Distance driven", `about ${km} km`]);
    if (started && ended) rows.push(["Time on the road", duration(new Date(ended) - new Date(started))]);
    rows.push(["Positions recorded", String(points.length)]);
    const dl = document.getElementById("facts");
    dl.replaceChildren(...rows.map(([k, v]) => {
      const row = ui.el("div");
      row.append(ui.el("dt", null, k), ui.el("dd", null, v));
      return row;
    }));
  }

  // Server times are UTC; show them in the phone's own time (Rwanda's).
  function time(iso) {
    return new Date(iso).toLocaleString("en-GB", {
      weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    });
  }

  function duration(ms) {
    const minutes = Math.round(ms / 60000);
    const h = Math.floor(minutes / 60);
    return h ? `${h} h ${minutes % 60} min` : `${minutes} min`;
  }
})();
