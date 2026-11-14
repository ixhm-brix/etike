// District map of Rwanda for the landing page, drawn as plain SVG so it
// matches the rest of the design (no map tiles, no map library).
// District shapes: geoBoundaries, CC BY 4.0 (assets/rwanda-districts.geojson).
// Road routes: the public OSRM demo server, OpenStreetMap data. It has usage
// limits, so switch to a self-hosted OSRM or a paid routing API at launch.

const RwandaMap = (() => {
  // Main town of each district as [latitude, longitude]. Routes start and
  // end here. Town centres are approximate; the router snaps them to a road.
  const TOWNS = {
    Kigali: [-1.9441, 30.0619],
    Bugesera: [-2.149, 30.093],
    Burera: [-1.468, 29.835],
    Gakenke: [-1.693, 29.784],
    Gatsibo: [-1.62, 30.4],
    Gicumbi: [-1.5763, 30.0675],
    Gisagara: [-2.62, 29.82],
    Huye: [-2.5967, 29.7394],
    Kamonyi: [-2.004, 29.897],
    Karongi: [-2.06, 29.348],
    Kayonza: [-1.9, 30.509],
    Kirehe: [-2.25, 30.67],
    Muhanga: [-2.085, 29.756],
    Musanze: [-1.499, 29.635],
    Ngoma: [-2.159, 30.543],
    Ngororero: [-1.865, 29.622],
    Nyabihu: [-1.625, 29.542],
    Nyagatare: [-1.297, 30.327],
    Nyamagabe: [-2.4833, 29.5667],
    Nyamasheke: [-2.3333, 29.0833],
    Nyanza: [-2.352, 29.751],
    Nyaruguru: [-2.64, 29.55],
    Rubavu: [-1.702, 29.256],
    Ruhango: [-2.223, 29.78],
    Rulindo: [-1.728, 29.993],
    Rusizi: [-2.484, 28.907],
    Rutsiro: [-1.93, 29.37],
    Rwamagana: [-1.949, 30.434],
  };

  // Kigali city is three districts; for travel it is one place.
  const KIGALI_PARTS = ["Nyarugenge", "Gasabo", "Kicukiro"];
  const placeOf = (district) => (KIGALI_PARTS.includes(district) ? "Kigali" : district);

  const DATA_URL = "assets/rwanda-districts.geojson";
  const ROUTER = "https://router.project-osrm.org/route/v1/driving/";
  const SVG_NS = "http://www.w3.org/2000/svg";
  const WIDTH = 600;
  const PAD = 14;

  const svgEl = (tag, attrs = {}) => {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
    return node;
  };

  // Rings of a GeoJSON Polygon or MultiPolygon, as [lon, lat] arrays.
  const ringsOf = (geom) =>
    geom.type === "Polygon" ? [geom.coordinates[0]] : geom.coordinates.map((p) => p[0]);

  // Area-weighted centre of a ring, for placing the district name.
  function centroid(ring) {
    let a = 0, x = 0, y = 0;
    for (let i = 0; i < ring.length - 1; i++) {
      const [x0, y0] = ring[i], [x1, y1] = ring[i + 1];
      const f = x0 * y1 - x1 * y0;
      a += f; x += (x0 + x1) * f; y += (y0 + y1) * f;
    }
    return [x / (3 * a), y / (3 * a)];
  }

  function render(container, { onPick } = {}) {
    const stage = document.createElement("div");
    stage.className = "rmap";
    container.append(stage);

    let project = null; // set once the district shapes have loaded
    let svg, routeLayer, endLayer, tagLayer, popup;
    const shapes = {}; // place name -> list of <path>
    const ready = fetch(DATA_URL)
      .then((res) => res.json())
      .then(draw)
      .catch(() => {
        stage.classList.add("rmap-unavailable");
        stage.textContent = "The map could not load. You can still search using the form.";
      });

    function draw(geo) {
      // Fit Rwanda's extent into the drawing.
      let minX = 180, maxX = -180, minY = 90, maxY = -90;
      geo.features.forEach((f) => ringsOf(f.geometry).forEach((r) => r.forEach(([x, y]) => {
        minX = Math.min(minX, x); maxX = Math.max(maxX, x);
        minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      })));
      const scale = (WIDTH - 2 * PAD) / (maxX - minX);
      const height = Math.round((maxY - minY) * scale + 2 * PAD);
      project = (lon, lat) => [PAD + (lon - minX) * scale, PAD + (maxY - lat) * scale];

      const toPath = (ring) =>
        "M" + ring.map(([x, y]) => project(x, y).map((n) => n.toFixed(1)).join(",")).join("L") + "Z";

      svg = svgEl("svg", {
        viewBox: `0 0 ${WIDTH} ${height}`,
        role: "group",
        "aria-label": "Map of Rwanda's districts. Choose a district to plan a trip.",
      });
      // Black outline underneath; the district fills cover all but the
      // outer edge, which leaves a crisp country border.
      const outline = svgEl("g", { class: "rmap-outline", "aria-hidden": "true" });
      const districts = svgEl("g", { class: "rmap-districts" });
      const labels = svgEl("g", { class: "rmap-labels", "aria-hidden": "true" });
      routeLayer = svgEl("g", { class: "rmap-route" });
      endLayer = svgEl("g", { class: "rmap-ends" });

      const kigaliCentres = [];
      geo.features.forEach((f) => {
        const name = f.properties.name;
        const place = placeOf(name);
        const rings = ringsOf(f.geometry);
        const d = rings.map(toPath).join("");
        outline.append(svgEl("path", { d }));

        const shape = svgEl("path", {
          d,
          tabindex: 0,
          role: "button",
          "aria-label": place === name ? name : `${name}, Kigali`,
          "data-place": place,
        });
        shape.addEventListener("click", (e) => openPopup(place, e));
        shape.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPopup(place, null, shape); }
        });
        districts.append(shape);
        (shapes[place] = shapes[place] || []).push(shape);

        // Label the biggest piece of each district at its centre.
        const main = rings.reduce((a, b) => (b.length > a.length ? b : a));
        const [cx, cy] = project(...centroid(main));
        if (place === "Kigali") { kigaliCentres.push([cx, cy]); return; }
        const t = svgEl("text", { x: cx.toFixed(1), y: (cy + 4).toFixed(1) });
        t.textContent = name;
        labels.append(t);
      });

      // One "Kigali" label for the three city districts.
      const kx = kigaliCentres.reduce((s, c) => s + c[0], 0) / kigaliCentres.length;
      const ky = kigaliCentres.reduce((s, c) => s + c[1], 0) / kigaliCentres.length;
      const kigali = svgEl("text", { x: kx.toFixed(1), y: (ky + 5).toFixed(1), class: "rmap-city" });
      kigali.textContent = "Kigali";
      labels.append(kigali);

      const [lx, ly] = project(29.08, -2.1);
      const lake = svgEl("text", { x: lx, y: ly, class: "rmap-water" });
      lake.textContent = "Lake Kivu";

      svg.append(outline, districts, lake, routeLayer, labels, endLayer);
      stage.append(svg);

      tagLayer = document.createElement("div");
      tagLayer.className = "rmap-tags";
      stage.append(tagLayer);

      popup = buildPopup();
      stage.append(popup);
    }

    // ---- "Leave from here / Go here" popup, in the page's own style ----

    function buildPopup() {
      const box = document.createElement("div");
      box.className = "rmap-pop";
      box.hidden = true;
      box.setAttribute("role", "dialog");
      const title = document.createElement("p");
      title.className = "rmap-pop-title";
      box.append(title);
      [["from", "Leave from here"], ["to", "Go here"]].forEach(([role, label]) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.dataset.role = role;
        btn.textContent = label;
        btn.addEventListener("click", () => {
          const place = box.dataset.place;
          closePopup();
          onPick && onPick(role, place);
        });
        box.append(btn);
      });
      document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePopup(); });
      document.addEventListener("click", (e) => {
        if (!box.hidden && !box.contains(e.target) && !svg.contains(e.target)) closePopup();
      });
      return box;
    }

    function openPopup(place, event, anchor) {
      const box = stage.getBoundingClientRect();
      let x, y;
      if (event) {
        x = event.clientX - box.left; y = event.clientY - box.top;
      } else {
        const r = anchor.getBoundingClientRect();
        x = r.left + r.width / 2 - box.left; y = r.top + r.height / 2 - box.top;
      }
      popup.dataset.place = place;
      popup.querySelector(".rmap-pop-title").textContent = place;
      // Keep the popup inside the map frame.
      popup.style.left = `${Math.min(Math.max(x, 90), box.width - 90)}px`;
      popup.style.top = `${y}px`;
      popup.classList.toggle("rmap-pop-below", y < 120);
      popup.hidden = false;
      popup.querySelector("button").focus({ preventScroll: true });
    }

    function closePopup() {
      if (popup) popup.hidden = true;
    }

    // ---- Trips ----

    let pending = null;

    function mark(from, to) {
      Object.values(shapes).flat().forEach((s) => s.classList.remove("is-from", "is-to"));
      (shapes[from] || []).forEach((s) => s.classList.add("is-from"));
      (shapes[to] || []).forEach((s) => s.classList.add("is-to"));
    }

    function tag(name, [x, y], kind) {
      const el = document.createElement("span");
      el.className = `rmap-tag rmap-tag-${kind}`;
      el.textContent = name;
      // Percentages keep the tag on its town at any map size.
      el.style.left = `${(x / WIDTH) * 100}%`;
      el.style.top = `${(y / svg.viewBox.baseVal.height) * 100}%`;
      tagLayer.append(el);
    }

    function drawLine(points, dashed) {
      const d = "M" + points.map((p) => p.map((n) => n.toFixed(1)).join(",")).join("L");
      if (!dashed) routeLayer.append(svgEl("path", { d, class: "rmap-casing" }));
      const line = svgEl("path", { d, class: dashed ? "rmap-line rmap-dashed" : "rmap-line", pathLength: 1 });
      // With non-scaling strokes the draw-in dash can fall short on long
      // routes, so drop it once the animation is done.
      line.addEventListener("animationend", () => line.classList.add("is-drawn"));
      routeLayer.append(line);
    }

    // Draw the trip between two places. Returns { km, minutes } or null.
    async function showTrip(from, to) {
      await ready;
      if (!project) return null;
      pending?.abort();
      routeLayer.replaceChildren();
      endLayer.replaceChildren();
      tagLayer.replaceChildren();
      mark(from, to);
      if (!from || !to || from === to) return null;

      const a = TOWNS[from];
      const b = TOWNS[to];
      const pa = project(a[1], a[0]);
      const pb = project(b[1], b[0]);

      pending = new AbortController();
      let result;
      try {
        const url = `${ROUTER}${a[1]},${a[0]};${b[1]},${b[0]}?overview=full&geometries=geojson`;
        const res = await fetch(url, { signal: pending.signal });
        const data = await res.json();
        const route = data.routes && data.routes[0];
        if (!route) throw new Error("No route");
        drawLine(route.geometry.coordinates.map(([lon, lat]) => project(lon, lat)), false);
        result = { km: route.distance / 1000, minutes: route.duration / 60 };
      } catch (err) {
        if (err.name === "AbortError") return null;
        // Router unreachable: a straight dashed line instead.
        drawLine([pa, pb], true);
        result = { offline: true };
      }

      // Start is a dot, destination a square, each with a name tag.
      endLayer.append(svgEl("circle", { cx: pa[0], cy: pa[1], r: 6, class: "rmap-start" }));
      endLayer.append(svgEl("rect", { x: pb[0] - 6, y: pb[1] - 6, width: 12, height: 12, rx: 1.5, class: "rmap-end" }));
      tag(from, pa, "from");
      tag(to, pb, "to");
      return result;
    }

    return { showTrip };
  }

  return { render, names: Object.keys(TOWNS) };
})();
