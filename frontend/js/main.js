// Landing page behaviour. Kept in its own file because the nginx security
// policy blocks inline scripts.

const MODE_CTA = {
  bus: "See bus options",
  car: "See car prices",
  shared: "Find a shared seat",
};

// Trip search form and the street map, kept in sync. This is the one search
// page, logged in or not: anyone can choose a route and see it on the map.
// Seeing prices needs an account, so a visitor goes to log in (or sign up)
// and comes straight back to the results with the same search.
(function tripSearch() {
  const form = document.getElementById("trip");
  if (!form) return;
  const { from, to, date } = form.elements;
  const cta = document.getElementById("trip-cta");
  const msg = document.getElementById("trip-msg");
  const seats = document.getElementById("seats-field");
  const summary = document.getElementById("trip-summary");
  const defaultSummary = summary.textContent;

  // Kigali first, then the other districts alphabetically.
  const names = ["Kigali", ...RwandaMap.names.filter((n) => n !== "Kigali").sort()];
  const options = (placeholder) =>
    `<option value="">${placeholder}</option>` +
    names.map((d) => `<option value="${d}">${d}</option>`).join("");
  from.innerHTML = options("Leaving from");
  to.innerHTML = options("Going to");

  const today = new Date().toISOString().slice(0, 10);
  date.min = today;

  // Start from the search in the address (from "Change search", or a link),
  // or from Kigali today.
  const params = new URLSearchParams(location.search);
  const pick = (select, value) => { if (names.includes(value)) select.value = value; };
  from.value = "Kigali";
  pick(from, params.get("origin"));
  pick(to, params.get("destination"));
  date.value = params.get("date") >= today ? params.get("date") : today;
  const mode = { private: "car", shared: "shared", bus: "bus" }[params.get("type")];
  if (mode && form.querySelector(`input[name="mode"][value="${mode}"]`)) form.elements.mode.value = mode;
  if (params.get("seats")) form.elements.seats.value = params.get("seats");

  const map = RwandaMap.render(document.getElementById("map-canvas"), {
    onPick(role, name) {
      const field = role === "from" ? from : to;
      const other = role === "from" ? to : from;
      if (other.value === name) other.value = "";
      field.value = name;
      sync();
    },
  });

  let lastTrip = "";

  async function updateMap() {
    const key = `${from.value}>${to.value}`;
    if (key === lastTrip) return;
    lastTrip = key;

    if (!from.value || !to.value || from.value === to.value) {
      summary.textContent = defaultSummary;
      map.showTrip(null, null);
      return;
    }
    summary.textContent = `Finding the road from ${from.value} to ${to.value}…`;
    const trip = await map.showTrip(from.value, to.value);
    if (key !== lastTrip) return; // the user changed the trip meanwhile
    if (!trip) return;
    if (trip.offline) {
      summary.textContent = `${from.value} to ${to.value}. Road distance is unavailable right now.`;
      return;
    }
    summary.textContent =
      `${from.value} to ${to.value}: about ${Math.round(trip.km)} km by road, ` +
      `roughly ${formatDuration(trip.minutes)} of driving. Estimated from OpenStreetMap.`;
  }

  function sync() {
    const mode = form.elements.mode.value;
    cta.textContent = MODE_CTA[mode];
    // A private car is booked whole, so the passenger count isn't needed.
    seats.hidden = mode === "car";
    msg.textContent = "";
    updateMap();
  }

  form.addEventListener("change", sync);
  sync();

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    msg.dataset.tone = "error";
    if (!from.value) { msg.textContent = "Choose where you are leaving from."; from.focus(); return; }
    if (!to.value) { msg.textContent = "Choose where you are going."; to.focus(); return; }
    if (from.value === to.value) { msg.textContent = "Pick two different districts."; return; }
    // The landing form's "car" is a private car in the API.
    const type = { bus: "bus", car: "private", shared: "shared" }[form.elements.mode.value];
    const query = new URLSearchParams({
      origin: from.value,
      destination: to.value,
      date: date.value,
      type,
      seats: form.elements.seats.value,
    });
    const results = `/results.html?${query}`;
    // Prices are for members: log in first, then land on these results.
    location.href = auth.user() ? results : `/login.html?next=${encodeURIComponent(results)}`;
  });
})();

function formatDuration(minutes) {
  const total = Math.round(minutes / 5) * 5;
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}
