// Search form. It only builds the results page address; results.js does the
// searching.
(async function search() {
  const form = document.getElementById("search");
  const msg = document.getElementById("msg");
  const { origin, destination, date } = form.elements;
  const params = new URLSearchParams(location.search);

  date.min = ui.today();
  date.value = params.get("date") || ui.today();
  if (params.get("type")) form.elements.type.value = params.get("type");

  try {
    await ui.fillPlaces(origin, "Leaving from", params.get("origin") || "Kigali");
    await ui.fillPlaces(destination, "Going to", params.get("destination"));
  } catch (err) {
    ui.say(msg, err.message);
  }

  form.addEventListener("submit", (e) => {
    if (!origin.value || !destination.value) {
      e.preventDefault();
      ui.say(msg, "Choose where you are leaving from and where you are going.");
    } else if (origin.value === destination.value) {
      e.preventDefault();
      ui.say(msg, "Pick two different places.");
    }
  });
})();
