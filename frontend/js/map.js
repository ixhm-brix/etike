// Draws the Rwanda route map on the landing page from real coordinates.
// Border and lake shapes are simplified by hand from public maps; town
// positions are the real latitude/longitude of each district's main town.

const RwandaMap = (() => {
  // [longitude, latitude], clockwise from Rubavu on Lake Kivu.
  const BORDER = [
    [29.24, -1.68], [29.30, -1.60], [29.37, -1.52], [29.45, -1.49], [29.53, -1.41],
    [29.60, -1.38], [29.72, -1.35], [29.83, -1.33], [29.93, -1.39], [30.02, -1.42],
    [30.10, -1.37], [30.18, -1.25], [30.28, -1.12], [30.36, -1.06], [30.47, -1.06],
    [30.57, -1.17], [30.67, -1.31], [30.75, -1.46], [30.82, -1.62], [30.85, -1.81],
    [30.89, -2.00], [30.86, -2.20], [30.81, -2.34], [30.78, -2.39], [30.65, -2.40],
    [30.53, -2.42], [30.42, -2.32], [30.30, -2.36], [30.15, -2.43], [30.03, -2.50],
    [29.96, -2.63], [29.92, -2.75], [29.80, -2.80], [29.68, -2.80], [29.56, -2.83],
    [29.44, -2.80], [29.31, -2.83], [29.16, -2.79], [29.03, -2.74], [28.97, -2.62],
    [28.90, -2.55], [28.87, -2.48], [28.98, -2.40], [29.05, -2.30], [29.12, -2.20],
    [29.22, -2.12], [29.30, -2.04], [29.33, -1.95], [29.30, -1.85], [29.27, -1.75],
  ];

  // Lake Kivu: the Rwandan shore (above) plus the western shore.
  const LAKE_KIVU = [
    [28.87, -2.48], [28.98, -2.40], [29.05, -2.30], [29.12, -2.20], [29.22, -2.12],
    [29.30, -2.04], [29.33, -1.95], [29.30, -1.85], [29.27, -1.75], [29.24, -1.68],
    [29.14, -1.66], [29.03, -1.78], [28.95, -1.98], [28.88, -2.18], [28.83, -2.36],
  ];

  // label: which side of the dot the name sits on.
  const PLACES = [
    { name: "Kigali", lon: 30.062, lat: -1.944, hub: true },
    { name: "Musanze", lon: 29.635, lat: -1.499, label: "right" },
    { name: "Rubavu", lon: 29.256, lat: -1.702, label: "left" },
    { name: "Karongi", lon: 29.348, lat: -2.060, label: "left" },
    { name: "Rusizi", lon: 28.907, lat: -2.484, label: "right" },
    { name: "Nyamagabe", lon: 29.570, lat: -2.470, label: "left" },
    { name: "Huye", lon: 29.739, lat: -2.597, label: "right" },
    { name: "Nyanza", lon: 29.751, lat: -2.352, label: "right" },
    { name: "Muhanga", lon: 29.756, lat: -2.085, label: "right" },
    { name: "Bugesera", lon: 30.093, lat: -2.149, label: "right" },
    { name: "Ngoma", lon: 30.543, lat: -2.159, label: "right" },
    { name: "Rwamagana", lon: 30.434, lat: -1.949, label: "right" },
    { name: "Nyagatare", lon: 30.327, lat: -1.297, label: "right" },
    { name: "Gicumbi", lon: 30.067, lat: -1.576, label: "right" },
  ];

  const SCALE = 280; // pixels per degree
  const ORIGIN = { lon: 28.72, lat: -0.98 };
  const WIDTH = Math.round((31.0 - ORIGIN.lon) * SCALE);
  const HEIGHT = Math.round((2.95 + ORIGIN.lat) * SCALE);
  const SVG_NS = "http://www.w3.org/2000/svg";

  const project = (lon, lat) => [(lon - ORIGIN.lon) * SCALE, (ORIGIN.lat - lat) * SCALE];

  // Closed smooth outline through the points (Catmull-Rom turned into Béziers).
  function smoothPath(coords) {
    const p = coords.map(([lon, lat]) => project(lon, lat));
    const n = p.length;
    let d = `M${p[0][0].toFixed(1)},${p[0][1].toFixed(1)}`;
    for (let i = 0; i < n; i++) {
      const p0 = p[(i - 1 + n) % n], p1 = p[i], p2 = p[(i + 1) % n], p3 = p[(i + 2) % n];
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
      const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += ` C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
    }
    return d + "Z";
  }

  // A gently curved line between two points, like a road on a map.
  function routePath(a, b) {
    const [x1, y1] = a, [x2, y2] = b;
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    const bend = 0.12;
    const cx = mx - (y2 - y1) * bend, cy = my + (x2 - x1) * bend;
    return `M${x1.toFixed(1)},${y1.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
  }

  const el = (tag, attrs = {}) => {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
  };

  function render(container, { onPick } = {}) {
    const svg = el("svg", {
      viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
      role: "img",
      "aria-label": "Map of Rwanda with routes from Kigali to 13 districts",
    });

    svg.append(el("path", { class: "map-land", d: smoothPath(BORDER) }));
    svg.append(el("path", { class: "map-lake", d: smoothPath(LAKE_KIVU) }));
    const lakeLabel = el("text", { class: "map-water", x: project(29.08, -2.0)[0], y: project(29.08, -2.0)[1] });
    lakeLabel.textContent = "Lake Kivu";
    svg.append(lakeLabel);

    const hub = PLACES.find((p) => p.hub);
    const hubXY = project(hub.lon, hub.lat);
    const routes = el("g", { class: "map-routes" });
    const pins = el("g", { class: "map-pins" });
    const byName = {};

    PLACES.filter((p) => !p.hub).forEach((place, i) => {
      const xy = project(place.lon, place.lat);
      const route = el("path", { d: routePath(hubXY, xy), pathLength: 1 });
      route.style.animationDelay = `${300 + i * 60}ms`;
      routes.append(route);

      const pin = el("g", { class: "map-pin", tabindex: 0, role: "button", "aria-label": `Go to ${place.name}` });
      pin.append(el("circle", { cx: xy[0], cy: xy[1], r: 12, class: "map-hit" }));
      pin.append(el("circle", { cx: xy[0], cy: xy[1], r: 5 }));
      const left = place.label === "left";
      const text = el("text", { x: xy[0] + (left ? -10 : 10), y: xy[1] + 4, "text-anchor": left ? "end" : "start" });
      text.textContent = place.name;
      pin.append(text);

      const pick = () => onPick && onPick(place.name);
      pin.addEventListener("click", pick);
      pin.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
      });
      pins.append(pin);
      byName[place.name] = { route, pin };
    });

    // Kigali: the square marker, like a pickup point.
    const hubG = el("g", { class: "map-hub" });
    hubG.append(el("rect", { x: hubXY[0] - 8, y: hubXY[1] - 8, width: 16, height: 16, rx: 2 }));
    const hubText = el("text", { x: hubXY[0] + 14, y: hubXY[1] - 10 });
    hubText.textContent = "Kigali";
    hubG.append(hubText);

    svg.append(routes, pins, hubG);
    container.prepend(svg);

    // Highlight one destination, or clear when the name has no pin.
    function highlight(name) {
      svg.classList.toggle("has-pick", Boolean(byName[name]));
      Object.entries(byName).forEach(([n, { route, pin }]) => {
        route.classList.toggle("is-picked", n === name);
        pin.classList.toggle("is-picked", n === name);
      });
    }

    return { highlight };
  }

  return { render, PLACES };
})();
