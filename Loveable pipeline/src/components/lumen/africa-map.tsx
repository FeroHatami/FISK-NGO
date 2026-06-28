import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useMarkers } from "@/lib/use-items";
import type { MapMarkerData } from "@/lib/api";
import { useLang, t } from "@/lib/i18n";

// Keep the old interface for backward compat with app.index.tsx
export interface MapMarker {
  id: string;
  label: string;
  cx: number;
  cy: number;
  count: number;
}

interface Props {
  markers: MapMarker[]; // region-level counts (still used for the legend)
  selected: string | null;
  onSelect: (id: string | null) => void;
  compact?: boolean;
}

const URGENCY_COLORS: Record<string, string> = {
  high: "#e53935",
  med: "#fb8c00",
  low: "#9e9e9e",
};

export function AfricaMap({ markers: regionMarkers, selected, onSelect, compact }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<unknown>(null);
  const [loaded, setLoaded] = useState(false);
  const { data: mapMarkers = [] } = useMarkers();
  const lang = useLang();

  // Load Leaflet CSS + JS from CDN once
  useEffect(() => {
    if (document.getElementById("leaflet-css")) {
      setLoaded(true);
      return;
    }
    const link = document.createElement("link");
    link.id = "leaflet-css";
    link.rel = "stylesheet";
    link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
    document.head.appendChild(link);

    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.onload = () => setLoaded(true);
    document.head.appendChild(script);
  }, []);

  // Initialize map
  useEffect(() => {
    if (!loaded || !mapRef.current) return;
    const L = (window as unknown as { L: typeof import("leaflet") }).L;
    if (!L) return;

    // Only init once
    if (leafletMapRef.current) return;

    const map = L.map(mapRef.current, {
      center: [-3.3, 29.9],
      zoom: 5,
      zoomControl: false,
      attributionControl: false,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 12,
    }).addTo(map);

    L.control.zoom({ position: "bottomright" }).addTo(map);

    leafletMapRef.current = map;

    return () => {
      map.remove();
      leafletMapRef.current = null;
    };
  }, [loaded]);

  // Update markers when data changes
  useEffect(() => {
    if (!leafletMapRef.current || !loaded) return;
    const L = (window as unknown as { L: typeof import("leaflet") }).L;
    const map = leafletMapRef.current as import("leaflet").Map;
    if (!L || !map) return;

    // Clear existing markers (layer group approach)
    map.eachLayer((layer: unknown) => {
      const l = layer as { options?: { pane?: string }; remove?: () => void };
      if (l.options?.pane === "markerPane" && l.remove) l.remove();
    });

    mapMarkers.forEach((m: MapMarkerData) => {
      const color = URGENCY_COLORS[m.urgency] || "#9e9e9e";
      const icon = L.divIcon({
        className: "leaflet-marker-custom",
        html: `<div style="width:14px;height:14px;background:${color};border:2px solid #fff;border-radius:50%;box-shadow:0 2px 4px rgba(0,0,0,.3);cursor:pointer;"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      });

      const itemsHtml = m.items
        .slice(0, 3)
        .map((i) => {
          const title = i.title.length > 44 ? i.title.slice(0, 44) + "…" : i.title;
          return `<div style="margin-top:3px;padding-top:3px;border-top:1px solid #eee;"><span style="font-weight:500;">${title}</span> <span style="color:#999;font-size:10px;">· ${i.urgency}</span></div>`;
        })
        .join("");

      const moreCount = m.count - Math.min(3, m.items.length);
      const moreHtml =
        moreCount > 0
          ? `<div style="margin-top:4px;color:#aaa;font-size:10px;">+${moreCount} more · click to filter</div>`
          : `<div style="margin-top:4px;color:#aaa;font-size:10px;">click to filter</div>`;

      const tooltipContent = `
        <div style="font-size:11px;width:160px;">
          <strong style="font-size:12px;">${m.name}</strong> <span style="color:#888;">· ${m.count}</span>
          ${itemsHtml}
          ${moreHtml}
        </div>
      `;

      const marker = L.marker([m.lat, m.lng], { icon }).addTo(map);

      // Hover tooltip with the location description
      marker.bindTooltip(tooltipContent, {
        direction: "auto",
        offset: [0, 0],
        opacity: 1,
        className: "lumen-map-tooltip",
        sticky: true,
      });

      marker.on("click", () => {
        // Filter by region matching this marker name
        const regionName = m.name;
        onSelect(selected === regionName ? null : regionName);
      });
    });
  }, [mapMarkers, loaded, selected, onSelect]);

  // Invalidate size when compact changes
  useEffect(() => {
    if (!leafletMapRef.current || !loaded) return;
    const map = leafletMapRef.current as import("leaflet").Map;
    setTimeout(() => map.invalidateSize(), 350);
  }, [compact, loaded]);

  return (
    <div className="relative w-full h-full flex flex-col isolate z-0">
      <div className="rounded-2xl bg-surface-elevated ring-1 ring-hairline/70 overflow-hidden flex flex-col h-full">
        {/* Header — hidden when compact */}
        <div
          className={cn(
            "overflow-hidden transition-all duration-300 ease-out",
            compact ? "max-h-0 opacity-0" : "max-h-24 opacity-100"
          )}
        >
          <div className="flex items-center justify-between px-4 py-2 border-b border-hairline/60">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-ink-faint">{t("map.fieldMap", lang)}</div>
              <div className="text-sm text-ink mt-0.5">
                {selected ? (
                  <>{t("home.filteringBy", lang)} <span className="font-medium">{selected}</span></>
                ) : (
                  <>{t("map.clickFilter", lang)}</>
                )}
              </div>
            </div>
            {selected && (
              <button
                onClick={() => onSelect(null)}
                className="text-xs text-ink-soft hover:text-ink rounded-full px-3 py-1 ring-1 ring-hairline/70 hover:ring-ink/30 transition"
              >
                {t("map.clear", lang)}
              </button>
            )}
          </div>
        </div>

        {/* Map container */}
        <div className="relative flex-1 min-h-0">
          <div ref={mapRef} className="w-full h-full" style={{ minHeight: "100%" }} />
          {!loaded && (
            <div className="absolute inset-0 flex items-center justify-center bg-muted/50">
              <span className="text-xs text-ink-faint">{t("map.loading", lang)}</span>
            </div>
          )}
        </div>

        {/* Region legend at bottom */}
        <div
          className={cn(
            "overflow-hidden transition-all duration-300 ease-out",
            compact ? "max-h-0 opacity-0" : "max-h-16 opacity-100"
          )}
        >
          <div className="flex items-center gap-3 px-4 py-2 border-t border-hairline/60 text-[11px] text-ink-faint">
            {regionMarkers.map((m) => (
              <button
                key={m.id}
                onClick={() => onSelect(selected === m.id ? null : m.id)}
                className={cn(
                  "inline-flex items-center gap-1 hover:text-ink transition",
                  selected === m.id && "text-ink font-medium"
                )}
              >
                <span className="size-2 rounded-full bg-ink/50" />
                {m.label} ({m.count})
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
