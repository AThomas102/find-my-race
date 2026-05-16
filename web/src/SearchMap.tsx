import L from "leaflet";
import { useEffect, useMemo } from "react";
import { Circle, CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";

import "./SearchMap.css";

export type SearchMapMarker = {
  id: string;
  lat: number;
  lon: number;
  score: number;
  title: string;
};

type SearchMapProps = {
  open: boolean;
  onClose: () => void;
  center: { lat: number; lon: number };
  radiusKm: number;
  markers: SearchMapMarker[];
};

const ACCENT = "#5eead4";
const ACCENT_SOFT = "#34d399";

function scoreStyle(
  score: number,
  minScore: number,
  maxScore: number,
): { radius: number; weight: number; fillOpacity: number; opacity: number } {
  const span = maxScore - minScore || 1;
  const t = (score - minScore) / span;
  return {
    radius: 4 + t * 4.5,
    weight: 1.5 + t * 1.75,
    fillOpacity: 0.38 + t * 0.28,
    opacity: 0.72 + t * 0.22,
  };
}

function buildBounds(center: { lat: number; lon: number }, radiusKm: number, markers: SearchMapMarker[]): L.LatLngBounds {
  const origin: [number, number] = [center.lat, center.lon];
  let b = L.latLngBounds(origin, origin);
  for (const m of markers) {
    b = b.extend([m.lat, m.lon]);
  }
  const latPad = radiusKm / 111.32;
  const cosLat = Math.cos((center.lat * Math.PI) / 180);
  const lonPad = radiusKm / (111.32 * Math.max(Math.abs(cosLat), 0.2));
  b = b.extend([center.lat + latPad, center.lon + lonPad]);
  b = b.extend([center.lat - latPad, center.lon - lonPad]);
  return b;
}

function FitBounds({ bounds, center }: { bounds: L.LatLngBounds; center: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    if (!bounds.isValid()) {
      map.setView(center, 9);
      return;
    }
    map.fitBounds(bounds, { padding: [32, 32], maxZoom: 12 });
  }, [bounds, center, map]);
  return null;
}

export function SearchMap({ open, onClose, center, radiusKm, markers }: SearchMapProps) {
  const mapCenter: [number, number] = [center.lat, center.lon];

  const bounds = useMemo(
    () => buildBounds(center, radiusKm, markers),
    [center.lat, center.lon, radiusKm, markers],
  );

  const { minScore, maxScore } = useMemo(() => {
    if (!markers.length) return { minScore: 0, maxScore: 1 };
    const xs = markers.map((m) => m.score);
    return { minScore: Math.min(...xs), maxScore: Math.max(...xs) };
  }, [markers]);

  const sortedMarkers = useMemo(() => [...markers].sort((a, b) => a.score - b.score), [markers]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="search-map-backdrop" role="presentation" onClick={onClose}>
      <div
        className="search-map-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="search-map-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="search-map-header">
          <h2 id="search-map-title">Results map</h2>
          <button type="button" className="search-map-close" onClick={onClose} autoFocus aria-label="Close map">
            Close
          </button>
        </div>
        <p className="search-map-caption">
          Search centre and {radiusKm} km radius — {markers.length} race{markers.length === 1 ? "" : "s"} on the map.
          Marker size reflects match score (subtle).
        </p>
        <div className="search-map-viewport">
          <MapContainer center={mapCenter} zoom={9} className="search-map-leaflet" scrollWheelZoom>
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              subdomains="abcd"
            />
            <FitBounds bounds={bounds} center={mapCenter} />
            <Circle
              center={mapCenter}
              radius={radiusKm * 1000}
              pathOptions={{
                color: ACCENT,
                weight: 2,
                opacity: 0.5,
                fillColor: ACCENT,
                fillOpacity: 0.07,
              }}
            />
            <CircleMarker
              center={mapCenter}
              radius={7}
              pathOptions={{
                color: ACCENT,
                weight: 3,
                fillColor: "#e8ecf6",
                fillOpacity: 0.95,
              }}
            />
            {sortedMarkers.map((m) => {
              const st = scoreStyle(m.score, minScore, maxScore);
              return (
                <CircleMarker
                  key={m.id}
                  center={[m.lat, m.lon]}
                  radius={st.radius}
                  pathOptions={{
                    color: ACCENT,
                    weight: st.weight,
                    fillColor: ACCENT_SOFT,
                    fillOpacity: st.fillOpacity,
                    opacity: st.opacity,
                  }}
                >
                  <Tooltip direction="top" offset={[0, -6]} opacity={0.95} className="search-map-tooltip-wrap">
                    <div className="search-map-tip">
                      <span className="search-map-tip-title">{m.title}</span>
                      <span className="search-map-tip-score">Score {m.score.toFixed(2)}</span>
                    </div>
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </MapContainer>
        </div>
      </div>
    </div>
  );
}
