import { useCallback, useEffect, useMemo, useState } from "react";

import { SearchMap, type SearchMapMarker } from "./SearchMap";
import "./App.css";

type Coordinates = { lat: number; lon: number };

type SearchResponse = {
  count: number;
  results: Array<{
    composite_score: number;
    distance_km: number | null;
    user_equiv_5k_sec: number | null;
    field_delta_sec: number | null;
    reasons: string[];
    race: {
      id: string;
      title: string;
      start: string;
      region: string | null;
      location_label: string | null;
      country?: string | null;
      postal_prefix?: string | null;
      course: {
        distance_m: number | null;
        surface: string;
        terrain: string;
        elevation_gain_m: number | null;
      };
      field_summary: {
        median_5k_sec: number | null;
        sample_size: number | null;
        provenance: string;
      } | null;
      sign_up_url: string | null;
      results_url?: string | null;
      coordinates?: { lat: number; lon: number } | null;
      metadata?: Record<string, unknown>;
    };
  }>;
};

/** Hampshire-first map presets (Southampton, Winchester, Portsmouth, etc.). */
const UK_PRESETS: { label: string; lat: number; lon: number }[] = [
  { label: "Southampton", lat: 50.9097, lon: -1.4044 },
  { label: "Winchester", lat: 51.0632, lon: -1.308 },
  { label: "Portsmouth", lat: 50.8198, lon: -1.0878 },
  { label: "Basingstoke", lat: 51.2667, lon: -1.0876 },
  { label: "Bournemouth (Dorset, neighbour)", lat: 50.7192, lon: -1.8808 },
];

const DISTANCE_PRESETS: { label: string; metres: number }[] = [
  { label: "5 km", metres: 5000 },
  { label: "10 km", metres: 10000 },
  { label: "Half marathon", metres: 21097 },
  { label: "Marathon", metres: 42195 },
];

function parseRaceTime(input: string): number | null {
  const s = input.trim();
  if (!s) return null;
  const parts = s.split(":").map((p) => Number(p.trim()));
  if (parts.some((n) => Number.isNaN(n))) return null;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return null;
}

function formatMinSec(sec: number | null | undefined): string {
  if (sec == null || Number.isNaN(sec)) return "—";
  const m = Math.floor(sec / 60);
  const r = Math.round(sec % 60);
  return `${m}:${r.toString().padStart(2, "0")}`;
}

function formatRaceDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDistanceLabel(metres: number | null | undefined): string | null {
  if (!metres) return null;
  if (metres >= 40000) return "Marathon";
  if (metres >= 20000) return "Half marathon";
  if (metres >= 9000 && metres <= 11000) return "10K";
  if (metres >= 4500 && metres <= 5500) return "5K";
  return `${(metres / 1000).toFixed(1)} km`;
}

function buildQuery(params: URLSearchParams) {
  return `/api/search?${params.toString()}`;
}

function formatApiError(status: number, text: string): string {
  if (status === 422 && text.trim().startsWith("{")) {
    try {
      const body = JSON.parse(text) as {
        detail?: Array<{ msg?: string } | string> | { msg?: string } | string;
      };
      const d = body.detail;
      if (Array.isArray(d)) {
        const parts = d
          .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: string }).msg) : ""))
          .filter(Boolean);
        if (parts.length) return parts.join(" ");
      }
      if (typeof d === "string") return d;
    } catch {
      /* fall through */
    }
  }
  return text.trim() || `Request failed (${status})`;
}

export default function App() {
  const [q, setQ] = useState("");
  const [region, setRegion] = useState("");
  const [presetIdx, setPresetIdx] = useState(0);
  const [radiusKm, setRadiusKm] = useState(65);
  const [distanceIdx, setDistanceIdx] = useState(1);
  const [customDistanceKm, setCustomDistanceKm] = useState("");
  const [raceTime, setRaceTime] = useState("");
  const [terrain, setTerrain] = useState<"any" | "flat" | "undulating" | "hilly">("any");
  const [surface, setSurface] = useState<"any" | "road" | "trail" | "track" | "mixed">("any");
  const [fieldWeight, setFieldWeight] = useState(0.55);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [lastSearchGeo, setLastSearchGeo] = useState<{ center: Coordinates; radiusKm: number } | null>(null);

  const centre: Coordinates = useMemo(() => {
    const p = UK_PRESETS[presetIdx] ?? UK_PRESETS[0];
    return { lat: p.lat, lon: p.lon };
  }, [presetIdx]);

  const mapMarkers: SearchMapMarker[] = useMemo(() => {
    if (!data) return [];
    const out: SearchMapMarker[] = [];
    for (const row of data.results) {
      const c = row.race.coordinates;
      if (c == null) continue;
      if (typeof c.lat !== "number" || typeof c.lon !== "number") continue;
      if (!Number.isFinite(c.lat) || !Number.isFinite(c.lon)) continue;
      out.push({
        id: row.race.id,
        lat: c.lat,
        lon: c.lon,
        score: row.composite_score,
        title: row.race.title,
      });
    }
    return out;
  }, [data]);

  const myDistanceM = useMemo(() => {
    const custom = Number(customDistanceKm);
    if (customDistanceKm.trim() !== "" && !Number.isNaN(custom) && custom > 0) {
      return Math.round(custom * 1000);
    }
    return DISTANCE_PRESETS[distanceIdx]?.metres ?? 10000;
  }, [customDistanceKm, distanceIdx]);

  const runSearch = useCallback(async () => {
    const t = parseRaceTime(raceTime);
    if (t != null && myDistanceM < 400) {
      setData(null);
      setLastSearchGeo(null);
      setError("Use at least 400 m distance when supplying a handicap time.");
      return;
    }
    const geoForRequest = { center: { lat: centre.lat, lon: centre.lon }, radiusKm };
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (region.trim()) params.set("region", region.trim());
    params.set("center_lat", String(geoForRequest.center.lat));
    params.set("center_lon", String(geoForRequest.center.lon));
    params.set("radius_km", String(geoForRequest.radiusKm));
    params.set("max_results", "72");
    if (t != null) {
      params.set("my_distance_m", String(myDistanceM));
      params.set("my_time_sec", String(t));
    }
    params.set("prefer_terrain", terrain);
    params.set("prefer_surface", surface);
    params.set("field_weight", String(fieldWeight));

    try {
      const res = await fetch(buildQuery(params));
      if (!res.ok) {
        const text = await res.text();
        throw new Error(formatApiError(res.status, text));
      }
      const json = (await res.json()) as SearchResponse;
      setLastSearchGeo(geoForRequest);
      setData(json);
    } catch (e) {
      setData(null);
      setLastSearchGeo(null);
      setError(e instanceof Error ? e.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }, [
    centre.lat,
    centre.lon,
    customDistanceKm,
    distanceIdx,
    fieldWeight,
    myDistanceM,
    q,
    raceTime,
    radiusKm,
    region,
    surface,
    terrain,
  ]);

  useEffect(() => {
    void runSearch();
    // Initial catalogue load only (Southampton hub, 65 km).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page">
      <header className="hero">
        <h1>Hampshire &amp; South Coast — find a race and sign up fast.</h1>
        <p>
          Search from a local hub, open <strong>Sign up</strong> or <strong>Past results</strong> on each card. Add a
          recent race time only if you want pace vs field matching — leave it empty to browse by place and map.
        </p>
      </header>

      <section className="panel">
        <h2>Search</h2>
        <div className="form-grid form-grid-primary">
          <label>
            Keywords
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. half, Portsmouth, 10k…" />
          </label>
          <label>
            Near
            <select value={presetIdx} onChange={(e) => setPresetIdx(Number(e.target.value))}>
              {UK_PRESETS.map((p, i) => (
                <option key={p.label} value={i}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Radius (km)
            <input
              type="number"
              min={5}
              max={120}
              value={radiusKm}
              onChange={(e) => setRadiusKm(Number(e.target.value))}
            />
          </label>
          <label>
            Region filter (optional)
            <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="Hampshire" />
          </label>
        </div>
        <details className="search-advanced">
          <summary>Pace matching (optional)</summary>
          <div className="form-grid">
          <label className="stack">
            Recent race distance
            <select value={distanceIdx} onChange={(e) => setDistanceIdx(Number(e.target.value))}>
              {DISTANCE_PRESETS.map((d, i) => (
                <option key={d.label} value={i}>
                  {d.label}
                </option>
              ))}
            </select>
            <input
              type="number"
              min={0.5}
              step={0.1}
              value={customDistanceKm}
              onChange={(e) => setCustomDistanceKm(e.target.value)}
              placeholder="Custom distance (km), optional override"
            />
          </label>
          <label className="stack">
            Finish time
            <input value={raceTime} onChange={(e) => setRaceTime(e.target.value)} placeholder="48:30 or leave blank" />
          </label>
          <label>
            Terrain
            <select
              value={terrain}
              onChange={(e) => setTerrain(e.target.value as typeof terrain)}
            >
              <option value="any">Any</option>
              <option value="flat">Mostly flat</option>
              <option value="undulating">Undulating</option>
              <option value="hilly">Hilly</option>
            </select>
          </label>
          <label>
            Surface
            <select
              value={surface}
              onChange={(e) => setSurface(e.target.value as typeof surface)}
            >
              <option value="any">Any</option>
              <option value="road">Road</option>
              <option value="trail">Trail</option>
              <option value="track">Track</option>
              <option value="mixed">Mixed</option>
            </select>
          </label>
          <label>
            Balance: location ↔ field match
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={fieldWeight}
              onChange={(e) => setFieldWeight(Number(e.target.value))}
            />
            <span className="hint">Field weight {Math.round(fieldWeight * 100)}%</span>
          </label>
          </div>
        </details>
        <div className="row-actions">
          <button className="primary" type="button" onClick={() => void runSearch()} disabled={loading}>
            {loading ? "Searching…" : "Search races"}
          </button>
        </div>
        {error ? <div className="error">{error}</div> : null}
      </section>

      {loading && !data ? <p className="hint results-loading">Loading local races…</p> : null}

      {data ? (
        <section className="results">
          <div className="results-toolbar">
            <button
              type="button"
              className="map-trigger"
              disabled={mapMarkers.length === 0}
              onClick={() => setMapOpen(true)}
            >
              Show map
            </button>
            {mapMarkers.length === 0 ? (
              <span className="hint">No races with map coordinates in this result set.</span>
            ) : null}
          </div>
          {lastSearchGeo && (
            <SearchMap
              open={mapOpen}
              onClose={() => setMapOpen(false)}
              center={lastSearchGeo.center}
              radiusKm={lastSearchGeo.radiusKm}
              markers={mapMarkers}
            />
          )}
          <p className="results-count">
            <strong>{data.count}</strong> race{data.count === 1 ? "" : "s"} match
            {data.results.some((r) => r.user_equiv_5k_sec != null) ? (
              <>
                {" "}
                · your equiv. 5K from that pace:{" "}
                <strong>
                  {formatMinSec(data.results.find((r) => r.user_equiv_5k_sec != null)?.user_equiv_5k_sec ?? null)}
                </strong>
              </>
            ) : null}
          </p>
          {data.results.map((row) => (
            <article key={row.race.id} className="card">
              <header className="card-head">
                <div>
                  <h3>{row.race.title}</h3>
                  <p className="card-sub">
                    {formatRaceDate(row.race.start)}
                    {" · "}
                    {row.race.location_label ?? row.race.region ?? "—"}
                    {row.distance_km != null ? ` · ~${row.distance_km.toFixed(0)} km` : ""}
                  </p>
                </div>
                {formatDistanceLabel(row.race.course.distance_m) ? (
                  <span className="badge distance-badge">{formatDistanceLabel(row.race.course.distance_m)}</span>
                ) : null}
              </header>
              <div className="card-actions">
                {row.race.sign_up_url ? (
                  <a className="btn-signup" href={row.race.sign_up_url} target="_blank" rel="noopener noreferrer">
                    Sign up
                  </a>
                ) : null}
                {row.race.results_url ? (
                  <a className="btn-results" href={row.race.results_url} target="_blank" rel="noopener noreferrer">
                    Past results
                  </a>
                ) : null}
                {!row.race.sign_up_url && !row.race.results_url ? (
                  <span className="hint thin">No organiser links on file for this listing.</span>
                ) : null}
              </div>
              {row.race.field_summary?.median_5k_sec != null ? (
                <div className="meta">
                  <span>
                    Typical field (median equiv. 5K):{" "}
                    <strong>{formatMinSec(row.race.field_summary.median_5k_sec)}</strong>
                  </span>
                  {row.field_delta_sec != null ? (
                    <span>
                      vs you: {row.field_delta_sec > 0 ? "+" : ""}
                      {formatMinSec(Math.abs(row.field_delta_sec))} on 5K equivalent
                    </span>
                  ) : null}
                  {row.race.field_summary.sample_size ? (
                    <span className="badge">n ≈ {row.race.field_summary.sample_size}</span>
                  ) : null}
                  <span className="badge">{row.race.field_summary.provenance.replaceAll("_", " ")}</span>
                </div>
              ) : (
                <p className="hint thin">No field stats yet — add chip times via ingest when you have them.</p>
              )}
              <details className="match-reasons">
                <summary>More detail</summary>
                <ul>
                  {row.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <p className="hint thin">Match score {row.composite_score.toFixed(2)}</p>
              </details>
            </article>
          ))}
        </section>
      ) : null}
    </div>
  );
}
