const STYLES = {
  county: { color: "#3e4c59", weight: 2, dashArray: "6 4", fill: false },
  // Corridors are thin at county zoom, so the outline carries the tier color.
  High: { color: "#ea580c", weight: 3, fillColor: "#ea580c", fillOpacity: 0.6 },
  Medium: { color: "#f5b014", weight: 3, fillColor: "#fbbf24", fillOpacity: 0.55 },
  Low: { color: "#a8a29e", weight: 2.5, fillColor: "#d6d3d1", fillOpacity: 0.55 },
  trailExisting: { color: "#15803d", weight: 3 },
  trailProposed: { color: "#15803d", weight: 3, dashArray: "6 6" },
  greenways: { color: "#065f46", weight: 4 },
  bikeExisting: { color: "#2563eb", weight: 3 },
  bikeFuture: { color: "#2563eb", weight: 3, dashArray: "6 6" },
};

const LABELS = {
  name: "Name",
  system: "System",
  status: "Status",
  type: "Type",
  surface: "Surface",
  width_ft: "Width (ft)",
  miles: "Miles",
  owner: "Owner",
  extent: "Extent",
  year: "Year",
  description: "Description",
  facility: "Facility",
  side: "Side of road",
  dept: "Dept",
};

const FACTORS = {
  connectivity: "Connects networks",
  landowners: "Few easement deeds",
  planned: "Near planned facility",
  width: "Corridor width",
  length: "Length",
};

// Extra click tolerance: corridors are only a few pixels wide at county zoom.
const map = L.map("map", { renderer: L.canvas({ tolerance: 6 }), zoomSnap: 0.25 });

const basemaps = {
  OpenStreetMap: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }),
  Satellite: L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 19, attribution: "Imagery &copy; Esri" },
  ),
};
basemaps.OpenStreetMap.addTo(map);

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function featurePopup(title) {
  return (layer) => {
    const props = layer.feature.properties;
    const rows = Object.entries(props)
      .filter(([key, value]) => key in LABELS && key !== "name" && value !== null && value !== "")
      .map(([key, value]) => `<tr><th>${LABELS[key]}</th><td>${escapeHtml(value)}</td></tr>`)
      .join("");
    const name = props.name ? escapeHtml(props.name) : title;
    return `<div class="popup"><h3>${name}</h3><table>${rows}</table></div>`;
  };
}

function segmentPopup(weights) {
  return (layer) => {
    const p = layer.feature.properties;
    const bars = Object.entries(FACTORS)
      .map(([key, label]) => {
        const pts = p[`pts_${key}`];
        const pct = (100 * pts) / weights[key];
        return `<tr><th>${label}</th>
          <td class="bar"><span style="width:${pct}%"></span></td>
          <td class="pts">${pts}/${weights[key]}</td></tr>`;
      })
      .join("");
    const detail = (label, value) =>
      value === null || value === "" ? "" : `<tr><th>${label}</th><td>${escapeHtml(value)}</td></tr>`;
    const deeds = `${p.deeds} (${p.deeds_per_mile} per mile)`;
    const trailInside = p.trail_inside_ft > 0 ? `${Math.round(p.trail_inside_ft).toLocaleString()} ft` : null;
    return `<div class="popup">
      <h3>Segment ${p.id} <span class="tier tier-${p.tier}">${p.tier}</span> ${p.score}/100</h3>
      ${p.networks >= 2 ? `<p class="flag">Links ${p.networks} separate trail/bike networks</p>` : ""}
      <table class="score">${bars}</table>
      <table>
        ${detail("Length", `${p.miles} mi`)}
        ${detail("Avg. width", `${p.width_ft} ft`)}
        ${detail("Easement deeds", deeds)}
        ${detail("Reaches", p.connects)}
        ${detail("Planned nearby", p.planned)}
        ${detail("Trail already inside", trailInside)}
        ${detail("Service", p.service)}
        ${p.in_county ? "" : detail("Location", "Outside Durham County")}
      </table></div>`;
  };
}

function lines(data, style, title, filter) {
  return L.geoJSON(data, { style, filter }).bindPopup(featurePopup(title));
}

async function load(name) {
  const resp = await fetch(`data/${name}.geojson`);
  return resp.json();
}

function addLegend() {
  const legend = L.control({ position: "bottomright" });
  const line = (s) => `<span class="swatch${s.dashArray ? " dashed" : ""}" style="border-color:${s.color}"></span>`;
  const fill = (s) =>
    `<span class="swatch fill" style="background:${s.fillColor};border-color:${s.color}"></span>`;
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `
      <h4>Easement trail feasibility</h4>
      ${fill(STYLES.High)}High (60+)<br>
      ${fill(STYLES.Medium)}Medium (40–59)<br>
      ${fill(STYLES.Low)}Low (&lt;40)<br>
      <h4>Trails &amp; bikeways</h4>
      ${line(STYLES.trailExisting)}Existing trail<br>
      ${line(STYLES.trailProposed)}Proposed trail<br>
      ${line(STYLES.greenways)}Greenway<br>
      ${line(STYLES.bikeExisting)}Bike facility<br>
      ${line(STYLES.bikeFuture)}Future bike facility`;
    return div;
  };
  legend.addTo(map);
}

async function main() {
  const meta = await (await fetch("data/meta.json")).json();
  map.fitBounds(meta.bounds);
  document.getElementById("as-of").textContent = `Data as of ${meta.data_as_of}.`;

  const [county, segments, trails, greenways, bikeExisting, bikeFuture] = await Promise.all(
    ["county", "segments", "trails", "greenways", "bike_existing", "bike_future"].map(load),
  );

  const isProposed = (f) => f.properties.status === "Proposed";
  const tier = (name) =>
    L.geoJSON(segments, { style: STYLES[name], filter: (f) => f.properties.tier === name })
      .bindPopup(segmentPopup(meta.summary.weights), { minWidth: 260, maxWidth: 340 });

  const overlays = {
    "Durham County": L.geoJSON(county, { style: STYLES.county, interactive: false }),
    "Low feasibility": tier("Low"),
    "Medium feasibility": tier("Medium"),
    "High feasibility": tier("High"),
    "Existing trails": lines(trails, STYLES.trailExisting, "Trail", (f) => !isProposed(f)),
    "Proposed trails": lines(trails, STYLES.trailProposed, "Proposed trail", isProposed),
    Greenways: lines(greenways, STYLES.greenways, "Greenway"),
    "Bike facilities": lines(bikeExisting, STYLES.bikeExisting, "Bike facility"),
    "Future bike facilities": lines(bikeFuture, STYLES.bikeFuture, "Future bike facility"),
  };
  for (const [label, layer] of Object.entries(overlays)) {
    if (layer.getLayers().length === 0) delete overlays[label];
    else layer.addTo(map);
  }

  L.control.layers(basemaps, overlays, { collapsed: window.innerWidth < 600 }).addTo(map);
  L.control.scale({ imperial: true, metric: false }).addTo(map);
  addLegend();
}

main();
