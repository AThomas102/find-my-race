import { useMemo, useState } from "react";
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
    };
  }>;
};

const UK_PRESETS: { label: string; lat: number; lon: number }[] = [
  { label: "London (centre)", lat: 51.5074, lon: -0.1278 },
  { label: "Manchester", lat: 53.4808, lon: -2.2426 },
  { label: "Birmingham", lat: 52.4862, lon: -1.8904 },
  { label: "Edinburgh", lat: 55.9533, lon: -3.1883 },
  { label: "Cardiff", lat: 51.4816, lon: -3.1791 },
  { label: "Bristol", lat: 51.4545, lon: -2.5879 },
  { label: "Southampton", lat: 50.9097, lon: -1.4044 },
  { label: "Brighton", lat: 50.8225, lon: -0.1372 },
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

function buildQuery(params: URLSearchParams) {
  return `/api/search?${params.toString()}`;
}

export default function App() {
  const [q, setQ] = useState("");
  const [region, setRegion] = useState("");
  const [presetIdx, setPresetIdx] = useState(0);
  const [radiusKm, setRadiusKm] = useState(120);
  const [distanceIdx, setDistanceIdx] = useState(1);
  const [customDistanceKm, setCustomDistanceKm] = useState("");
  const [raceTime, setRaceTime] = useState("48:30");
  const [terrain, setTerrain] = useState<"any" | "flat" | "undulating" | "hilly">("any");
  const [surface, setSurface] = useState<"any" | "road" | "trail" | "track" | "mixed">("any");
  const [fieldWeight, setFieldWeight] = useState(0.55);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);

  const centre: Coordinates = useMemo(() => {
    const p = UK_PRESETS[presetIdx] ?? UK_PRESETS[0];
    return { lat: p.lat, lon: p.lon };
  }, [presetIdx]);

  const myDistanceM = useMemo(() => {
    const custom = Number(customDistanceKm);
    if (customDistanceKm.trim() !== "" && !Number.isNaN(custom) && custom > 0) {
      return Math.round(custom * 1000);
    }
    return DISTANCE_PRESETS[distanceIdx]?.metres ?? 10000;
  }, [customDistanceKm, distanceIdx]);

  async function runSearch() {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (region.trim()) params.set("region", region.trim());
    params.set("center_lat", String(centre.lat));
    params.set("center_lon", String(centre.lon));
    params.set("radius_km", String(radiusKm));
    params.set("max_results", "30");
    params.set("my_distance_m", String(myDistanceM));
    const t = parseRaceTime(raceTime);
    if (t != null) params.set("my_time_sec", String(t));
    params.set("prefer_terrain", terrain);
    params.set("prefer_surface", surface);
    params.set("field_weight", String(fieldWeight));

    try {
      const res = await fetch(buildQuery(params));
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Request failed (${res.status})`);
      }
      const json = (await res.json()) as SearchResponse;
      setData(json);
    } catch (e) {
      setData(null);
      setError(e instanceof Error ? e.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <h1>Find a race that fits you — not just your calendar.</h1>
        <p>
          Search by <strong>place</strong>, then tune with a <strong> recent race time</strong> to see events
          whose typical finishers look like <em>your</em> pace. Terrain and surface filters are early hooks
          for richer course intelligence later on.
        </p>
      </header>

      <section className="panel">
        <h2>Smart search</h2>
        <div className="form-grid">
          <label>
            Keywords
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. marathon, Vitality…" />
          </label>
          <label>
            Region (optional)
            <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="e.g. Hampshire" />
          </label>
          <label>
            Near (preset)
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
              max={500}
              value={radiusKm}
              onChange={(e) => setRadiusKm(Number(e.target.value))}
            />
          </label>
          <label className="stack">
            Your recent race
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
          <label>
            Time (hh:mm:ss or mm:ss)
            <input value={raceTime} onChange={(e) => setRaceTime(e.target.value)} placeholder="48:30" />
          </label>
          <label>
            Terrain preference
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
            Surface preference
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
            <span className="hint">
              Field weight {Math.round(fieldWeight * 100)}% — raise this to prioritise matching typical finishers.
            </span>
          </label>
        </div>
        <div className="row-actions">
          <button className="primary" type="button" onClick={() => void runSearch()} disabled={loading}>
            {loading ? "Searching…" : "Search races"}
          </button>
          <span className="hint">API: GET /api/search (see FastAPI docs at /docs on the backend).</span>
        </div>
        {error ? <div className="error">{error}</div> : null}
      </section>

      {data ? (
        <section className="results">
          <p className="hint">
            {data.count} result{data.count === 1 ? "" : "s"}
            {data.results.some((r) => r.user_equiv_5k_sec != null) ? (
              <>
                {" "}
                — your equivalent 5K is{" "}
                <strong>
                  {formatMinSec(
                    data.results.find((r) => r.user_equiv_5k_sec != null)?.user_equiv_5k_sec ?? null,
                  )}
                </strong>{" "}
                from the pace you entered (Riegel-style mapping in core; swap for VDOT later without changing
                the UI).
              </>
            ) : null}
          </p>
          {data.results.map((row) => (
            <article key={row.race.id} className="card">
              <header>
                <h3>{row.race.title}</h3>
                <span className="badge accent">score {row.composite_score.toFixed(2)}</span>
              </header>
              <div className="meta">
                <span>{new Date(row.race.start).toLocaleString()}</span>
                <span>{row.race.location_label ?? row.race.region ?? "—"}</span>
                {row.distance_km != null ? <span>~{row.distance_km} km away</span> : null}
                <span className="badge">
                  {row.race.course.terrain} · {row.race.course.surface}
                  {row.race.course.elevation_gain_m != null
                    ? ` · ~${row.race.course.elevation_gain_m} m climb`
                    : ""}
                </span>
                {row.race.course.distance_m ? (
                  <span className="badge">{(row.race.course.distance_m / 1000).toFixed(3)} km</span>
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
                <p className="hint">No field summary on this record — ingestion can attach one from results or entrants.</p>
              )}
              <ul className="reasons">
                {row.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {row.race.sign_up_url ? (
                <a href={row.race.sign_up_url} target="_blank" rel="noreferrer">
                  Event link (demo)
                </a>
              ) : null}
            </article>
          ))}
        </section>
      ) : null}
    </div>
  );
}
