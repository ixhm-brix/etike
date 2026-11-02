// Landing page behaviour. Kept in its own file because the nginx security
// policy blocks inline scripts.

// Kigali first, then Rwanda's other 27 districts.
const DISTRICTS = [
  "Kigali", "Bugesera", "Burera", "Gakenke", "Gatsibo", "Gicumbi", "Gisagara",
  "Huye", "Kamonyi", "Karongi", "Kayonza", "Kirehe", "Muhanga", "Musanze",
  "Ngoma", "Ngororero", "Nyabihu", "Nyagatare", "Nyamagabe", "Nyamasheke",
  "Nyanza", "Nyaruguru", "Rubavu", "Ruhango", "Rulindo", "Rusizi", "Rutsiro",
  "Rwamagana",
];

const MODE_CTA = {
  bus: "See bus options",
  car: "See car prices",
  shared: "Find a shared seat",
};

// Trip search form and the map, kept in sync.
(function tripSearch() {
  const form = document.getElementById("trip");
  if (!form) return;
  const { from, to, date } = form.elements;
  const cta = document.getElementById("trip-cta");
  const msg = document.getElementById("trip-msg");
  const seats = document.getElementById("seats-field");

  const options = (placeholder) =>
    `<option value="">${placeholder}</option>` +
    DISTRICTS.map((d) => `<option value="${d}">${d}</option>`).join("");
  from.innerHTML = options("Leaving from");
  to.innerHTML = options("Going to");
  from.value = "Kigali";

  const today = new Date().toISOString().slice(0, 10);
  date.min = today;
  date.value = today;

  // Routes on the map start in Kigali, so highlight whichever end isn't Kigali.
  const map = RwandaMap.render(document.getElementById("map"), {
    onPick(name) {
      to.value = name;
      if (from.value === name) from.value = "Kigali";
      sync();
      to.focus();
    },
  });

  function sync() {
    const mode = form.elements.mode.value;
    cta.textContent = MODE_CTA[mode];
    // A private car is booked whole, so the passenger count isn't needed.
    seats.hidden = mode === "car";
    const other = from.value === "Kigali" ? to.value : to.value === "Kigali" ? from.value : "";
    map.highlight(other);
    msg.textContent = "";
  }

  form.addEventListener("change", sync);
  sync();

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    msg.dataset.tone = "error";
    if (!from.value) { msg.textContent = "Choose where you are leaving from."; from.focus(); return; }
    if (!to.value) { msg.textContent = "Choose where you are going."; to.focus(); return; }
    if (from.value === to.value) { msg.textContent = "Pick two different districts."; return; }
    msg.dataset.tone = "info";
    msg.textContent = `Booking from ${from.value} to ${to.value} opens once we have collected real timetables and prices.`;
  });
})();
