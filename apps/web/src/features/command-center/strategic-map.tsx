"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { MapRegionFeature, SettlementMapMarker } from "../../lib/api";
import type { WorldSnapshot } from "./command-center.types";
import { formatLabel, formatNumber } from "./command-center.view";

type OverlayId = "population" | "food" | "tension" | "core" | "temporary" | "settlements";
type PathStyle = Record<string, string | number | boolean | undefined>;
type LeafletBounds = object;
type LeafletLayer = {
  addTo(map: LeafletMap): LeafletLayer;
  on(event: string, handler: () => void): LeafletLayer;
  setStyle?: (style: PathStyle) => void;
};
type LeafletMap = {
  fitBounds(bounds: LeafletBounds, options?: Record<string, unknown>): void;
  remove(): void;
  attributionControl: { addAttribution(value: string): void };
};
type LeafletNamespace = {
  CRS: { Simple: object };
  map(element: HTMLElement, options: Record<string, unknown>): LeafletMap;
  latLngBounds(points: [[number, number], [number, number]]): LeafletBounds;
  imageOverlay(url: string, bounds: LeafletBounds, options?: Record<string, unknown>): LeafletLayer;
  geoJSON(
    data: object,
    options: {
      style: () => PathStyle;
      onEachFeature: (feature: object, layer: LeafletLayer) => void;
    },
  ): LeafletLayer;
  divIcon(options: Record<string, unknown>): object;
  marker(position: [number, number], options: Record<string, unknown>): LeafletLayer;
};

declare global {
  interface Window {
    L?: LeafletNamespace;
    __cliovaLeafletPromise?: Promise<LeafletNamespace>;
  }
}

const LEAFLET_VERSION = "1.9.4";
const LEAFLET_CSS = `https://unpkg.com/leaflet@${LEAFLET_VERSION}/dist/leaflet.css`;
const LEAFLET_JS = `https://unpkg.com/leaflet@${LEAFLET_VERSION}/dist/leaflet.js`;
const overlayLabels: Array<[OverlayId, string]> = [
  ["population", "Population"],
  ["food", "Food"],
  ["tension", "Tension"],
  ["core", "Core presence"],
  ["temporary", "Seasonal access"],
  ["settlements", "Settlements"],
];

export function StrategicMap({
  world,
  selectedRegionId,
  onSelectRegion,
}: {
  world: WorldSnapshot;
  selectedRegionId: string;
  onSelectRegion: (regionId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const regionLayersRef = useRef(new Map<string, LeafletLayer>());
  const [overlays, setOverlays] = useState<Set<OverlayId>>(() => new Set(["settlements"]));
  const [runtimeState, setRuntimeState] = useState<"loading" | "ready" | "error">("loading");
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [baseError, setBaseError] = useState(false);
  const [selectedSettlementId, setSelectedSettlementId] = useState<string | null>(null);
  const mapData = world.map;

  const selectedRegion = world.regions.find((region) => region.id === selectedRegionId) ?? world.regions[0] ?? null;
  const selectedFeature = mapData.regions.find((region) => region.id === selectedRegion?.id) ?? null;
  const settlements = mapData.settlements.filter((settlement) => settlement.region_id === selectedRegion?.id);
  const selectedSettlement = mapData.settlements.find((settlement) => settlement.id === selectedSettlementId) ?? null;
  const regionHistory = world.feed.filter((item) => selectedRegion && item.regionIds.includes(selectedRegion.id)).slice(0, 3);
  const maxPopulation = useMemo(
    () => Math.max(1, ...mapData.regions.map((region) => region.population ?? 0)),
    [mapData.regions],
  );

  useEffect(() => {
    const baseMapUrl = mapData.base_map_url;
    if (!mapData.available || !containerRef.current || !baseMapUrl) {
      setRuntimeState(mapData.available ? "error" : "ready");
      return;
    }
    let cancelled = false;
    let map: LeafletMap | null = null;
    setRuntimeState("loading");
    setRuntimeError(null);
    setBaseError(false);

    void loadLeaflet().then((L) => {
      if (cancelled || !containerRef.current) return;
      const bounds = L.latLngBounds([[0, 0], [mapData.extent_height, mapData.extent_width]]);
      map = L.map(containerRef.current, {
        crs: L.CRS.Simple,
        minZoom: -3,
        maxZoom: 6,
        zoomSnap: 0.25,
        attributionControl: true,
      });
      mapRef.current = map;
      map.attributionControl.addAttribution(`Leaflet ${LEAFLET_VERSION} · non-Earth game coordinates`);
      L.imageOverlay(baseMapUrl, bounds, { interactive: false, zIndex: 1 })
        .on("error", () => setBaseError(true))
        .addTo(map);

      regionLayersRef.current.clear();
      for (const region of mapData.regions) {
        const layer = L.geoJSON(
          {
            type: "Feature",
            properties: { regionId: region.id },
            geometry: region.geometry,
          },
          {
            style: () => regionStyle(region, region.id === selectedRegionId, overlays, maxPopulation),
            onEachFeature: (_feature, featureLayer) => {
              featureLayer.on("click", () => onSelectRegion(region.id));
              featureLayer.on("mouseover", () => featureLayer.setStyle?.({ weight: 2.6, fillOpacity: 0.34 }));
              featureLayer.on("mouseout", () => featureLayer.setStyle?.(
                regionStyle(region, region.id === selectedRegionId, overlays, maxPopulation),
              ));
            },
          },
        ).addTo(map);
        regionLayersRef.current.set(region.id, layer);
      }

      if (overlays.has("settlements")) {
        for (const settlement of mapData.settlements) {
          const iconClass = settlement.archetype === "permanent" ? "permanent" : "camp";
          const marker = L.marker(
            [settlement.position[1], settlement.position[0]],
            {
              icon: L.divIcon({
                className: `strategic-settlement-icon ${iconClass} status-${settlement.status}`,
                html: '<span aria-hidden="true"></span>',
                iconSize: [18, 18],
                iconAnchor: [9, 9],
              }),
              keyboard: true,
              title: settlement.name,
              zIndexOffset: 500,
            },
          );
          marker.on("click", () => {
            setSelectedSettlementId(settlement.id);
            onSelectRegion(settlement.region_id);
          });
          marker.addTo(map);
        }
      }

      map.fitBounds(bounds, { padding: [16, 16] });
      setRuntimeState("ready");
    }).catch((error: unknown) => {
      if (cancelled) return;
      setRuntimeState("error");
      setRuntimeError(error instanceof Error ? error.message : "Leaflet could not be loaded.");
    });

    return () => {
      cancelled = true;
      map?.remove();
      if (mapRef.current === map) mapRef.current = null;
      regionLayersRef.current.clear();
    };
  }, [mapData, maxPopulation, onSelectRegion, overlays]);

  useEffect(() => {
    for (const region of mapData.regions) {
      regionLayersRef.current.get(region.id)?.setStyle?.(
        regionStyle(region, region.id === selectedRegionId, overlays, maxPopulation),
      );
    }
  }, [mapData.regions, maxPopulation, overlays, selectedRegionId]);

  function toggleOverlay(id: OverlayId) {
    setOverlays((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function fitWorld() {
    if (!mapRef.current || !mapData.available) return;
    void loadLeaflet().then((L) => {
      mapRef.current?.fitBounds(
        L.latLngBounds([[0, 0], [mapData.extent_height, mapData.extent_width]]),
        { padding: [16, 16] },
      );
    });
  }

  if (!mapData.available) {
    return (
      <div className="strategic-map-unavailable" role="status">
        <strong>Strategic geography unavailable</strong>
        <p>This persisted world has no #59 presentation geometry. Cliova will not substitute fake map positions.</p>
        <small>{mapData.unavailable_reason ?? "map unavailable"}</small>
      </div>
    );
  }

  return (
    <div className="strategic-map-workspace">
      <div className="strategic-map-stage">
        <div className="strategic-map-toolbar" aria-label="Strategic map overlays">
          <button type="button" onClick={fitWorld}>Fit world</button>
          {overlayLabels.map(([id, label]) => (
            <button
              type="button"
              key={id}
              aria-pressed={overlays.has(id)}
              className={overlays.has(id) ? "active" : ""}
              onClick={() => toggleOverlay(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div ref={containerRef} className="strategic-map-canvas" data-coordinate-system={mapData.coordinate_system} />
        {runtimeState === "loading" && <div className="strategic-map-state">Loading generated geography…</div>}
        {runtimeState === "error" && (
          <div className="strategic-map-state error" role="alert">
            Interactive map unavailable. {runtimeError ?? "Leaflet runtime failed to initialize."}
          </div>
        )}
        {baseError && (
          <div className="strategic-map-state warning" role="alert">
            Physical base render failed to load; authoritative region geometry remains available.
          </div>
        )}
        <div className="strategic-map-version">{mapData.render_version}</div>
      </div>

      <aside className="strategic-region-context" aria-label="Selected region context">
        <span className="eyebrow">Selected region</span>
        <h3>{selectedRegion?.label ?? "No region selected"}</h3>
        {selectedRegion && selectedFeature && (
          <>
            <p>{selectedRegion.terrain} · {selectedRegion.biome} · {formatLabel(selectedFeature.surface)}</p>
            <dl>
              <ContextStat label="Population" value={selectedRegion.population} />
              <ContextStat label="Food shortage" value={selectedRegion.food.shortageSeverity} />
              <ContextStat label="Tension" value={formatNumber(selectedFeature.pressure_intensity)} />
              <ContextStat label="Elevation" value={formatNumber(selectedFeature.mean_elevation)} />
            </dl>
            <ContextGroup title="Society presence">
              {selectedFeature.core_society_ids.length === 0 && selectedFeature.temporary_presence.length === 0 && <span>None projected.</span>}
              {selectedFeature.core_society_ids.map((societyId) => (
                <span key={`core-${societyId}`}>{societyLabel(world, societyId)} · core</span>
              ))}
              {selectedFeature.temporary_presence.map((presence) => (
                <span key={`${presence.society_id}-${presence.production_method}`}>
                  {societyLabel(world, presence.society_id)} · {formatLabel(presence.production_method)} · temporary {formatNumber(presence.access_share)}
                </span>
              ))}
            </ContextGroup>
            <ContextGroup title="Settlements / camps">
              {settlements.length === 0 && <span>None in authoritative settlement state.</span>}
              {settlements.map((settlement) => (
                <button type="button" key={settlement.id} onClick={() => setSelectedSettlementId(settlement.id)}>
                  {settlement.name} · {formatLabel(settlement.archetype)} · {settlement.population_estimate}
                </button>
              ))}
            </ContextGroup>
            <ContextGroup title="Recent here">
              {regionHistory.length === 0 && <span>No recent region-linked history.</span>}
              {regionHistory.map((item) => <span key={item.id}>{item.time} · {item.text}</span>)}
            </ContextGroup>
          </>
        )}

        {selectedSettlement && (
          <section className="strategic-settlement-summary">
            <span className="eyebrow">Settlement</span>
            <strong>{selectedSettlement.name}</strong>
            <small>
              {formatLabel(selectedSettlement.archetype)} · {formatLabel(selectedSettlement.status)} · population {selectedSettlement.population_estimate} · {selectedSettlement.structure_count} strategic structures
            </small>
            <a href={selectedSettlement.local_map_path}>Open local settlement map</a>
            <small>Local layout is owned by #61; this link is the strategic handoff only.</small>
          </section>
        )}
      </aside>
    </div>
  );
}

function ContextStat({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function ContextGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="strategic-context-group">
      <strong>{title}</strong>
      <div>{children}</div>
    </section>
  );
}

function societyLabel(world: WorldSnapshot, societyId: string): string {
  return world.societies.find((society) => society.id === societyId)?.label ?? `Society ${societyId.slice(0, 8)}`;
}

function regionStyle(
  region: MapRegionFeature,
  selected: boolean,
  overlays: Set<OverlayId>,
  maxPopulation: number,
): PathStyle {
  let fillColor = "#c7d0d6";
  let fillOpacity = 0.035;
  if (overlays.has("population") && region.population !== null) {
    fillColor = "#77b9a2";
    fillOpacity = 0.08 + (0.34 * Math.min(1, region.population / maxPopulation));
  }
  if (overlays.has("food") && region.food_shortage_severity !== null) {
    fillColor = "#d6a25b";
    fillOpacity = 0.08 + (0.36 * Math.min(1, region.food_shortage_severity));
  }
  if (overlays.has("tension") && region.pressure_intensity !== null) {
    fillColor = "#df746d";
    fillOpacity = 0.08 + (0.42 * Math.min(1, region.pressure_intensity));
  }

  const hasCore = overlays.has("core") && region.core_society_ids.length > 0;
  const hasTemporary = overlays.has("temporary") && region.temporary_presence.length > 0;
  return {
    color: selected ? "#f0c46d" : hasCore ? "#78d6a3" : hasTemporary ? "#72a9d1" : "#a4b1ba",
    weight: selected ? 2.5 : hasCore || hasTemporary ? 1.8 : 0.8,
    opacity: selected ? 1 : 0.66,
    dashArray: hasTemporary && !hasCore ? "3 4" : undefined,
    fillColor,
    fillOpacity,
  };
}

function loadLeaflet(): Promise<LeafletNamespace> {
  if (window.L) return Promise.resolve(window.L);
  if (window.__cliovaLeafletPromise) return window.__cliovaLeafletPromise;

  window.__cliovaLeafletPromise = new Promise<LeafletNamespace>((resolve, reject) => {
    if (!document.querySelector('link[data-cliova-leaflet="1.9.4"]')) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = LEAFLET_CSS;
      stylesheet.dataset.cliovaLeaflet = LEAFLET_VERSION;
      document.head.appendChild(stylesheet);
    }

    const existing = document.querySelector<HTMLScriptElement>('script[data-cliova-leaflet="1.9.4"]');
    const complete = () => {
      if (window.L) resolve(window.L);
      else reject(new Error("Leaflet 1.9.4 loaded without exposing its runtime API."));
    };
    if (existing) {
      existing.addEventListener("load", complete, { once: true });
      existing.addEventListener("error", () => reject(new Error("Leaflet 1.9.4 could not be loaded.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = LEAFLET_JS;
    script.async = true;
    script.dataset.cliovaLeaflet = LEAFLET_VERSION;
    script.addEventListener("load", complete, { once: true });
    script.addEventListener("error", () => reject(new Error("Leaflet 1.9.4 could not be loaded.")), { once: true });
    document.head.appendChild(script);
  });
  return window.__cliovaLeafletPromise;
}

export function settlementKind(marker: SettlementMapMarker): "permanent" | "camp" {
  return marker.archetype === "permanent" ? "permanent" : "camp";
}
