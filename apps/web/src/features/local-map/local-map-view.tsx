"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type { LocalMapFeature, LocalMapResult, LocalPoint } from "./local-map-generator";

export function LocalMapView({ result, worldId, settlementName }: {
  result: LocalMapResult;
  worldId: string;
  settlementName: string;
}) {
  const [zoom, setZoom] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const selected = useMemo(
    () => result.features.find((feature) => feature.feature_id === selectedId) ?? null,
    [result.features, selectedId],
  );
  const padding = 18;
  const width = Math.max(1, result.bounds.max_x - result.bounds.min_x + padding * 2);
  const height = Math.max(1, result.bounds.max_y - result.bounds.min_y + padding * 2);
  const viewBox = `${result.bounds.min_x - padding} ${result.bounds.min_y - padding} ${width} ${height}`;
  const mapped = result.structure_feature_mappings.filter((item) => item.status === "mapped").length;

  return (
    <main style={{ minHeight: "100vh", padding: "24px", background: "#131310", color: "#eee9dc" }}>
      <header style={{ display: "flex", gap: "16px", justifyContent: "space-between", alignItems: "start", marginBottom: "18px" }}>
        <div>
          <Link href="/" style={{ color: "inherit", opacity: 0.75 }}>← Back to world context</Link>
          <p style={{ margin: "14px 0 4px", opacity: 0.65, textTransform: "uppercase", letterSpacing: "0.12em", fontSize: "0.75rem" }}>
            Local map · {result.renderer === "settlemaker" ? "permanent settlement" : "temporary camp"}
          </p>
          <h1 style={{ margin: 0 }}>{settlementName}</h1>
          <p style={{ margin: "6px 0 0", opacity: 0.7 }}>
            {mapped}/{result.structure_feature_mappings.length} authoritative structures placed · seed {result.layout_seed}
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px" }} aria-label="Map zoom controls">
          <button type="button" onClick={() => setZoom((value) => Math.max(0.6, value - 0.2))}>−</button>
          <button type="button" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button>
          <button type="button" onClick={() => setZoom((value) => Math.min(3, value + 0.2))}>+</button>
        </div>
      </header>

      <section style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(240px, 320px)", gap: "16px", alignItems: "start" }}>
        <div
          aria-label={`Map of ${settlementName}`}
          style={{
            overflow: "auto",
            minHeight: "65vh",
            maxHeight: "75vh",
            border: "1px solid #4c493f",
            background: "#e6dcc7",
            borderRadius: "8px",
          }}
        >
          <svg
            viewBox={viewBox}
            role="img"
            aria-label={`${settlementName} local settlement geometry`}
            style={{ display: "block", width: `${zoom * 100}%`, minWidth: "100%", height: "auto" }}
          >
            {result.features.filter((feature) => feature.authority !== "authoritative_structure").map((feature) => (
              <MapFeatureShape key={feature.feature_id} feature={feature} active={hoveredId === feature.feature_id} />
            ))}
            {result.features.filter((feature) => feature.authority === "authoritative_structure").map((feature) => (
              <MapFeatureShape
                key={feature.feature_id}
                feature={feature}
                active={hoveredId === feature.feature_id || selectedId === feature.feature_id}
                interactive
                onEnter={() => setHoveredId(feature.feature_id)}
                onLeave={() => setHoveredId(null)}
                onSelect={() => setSelectedId(feature.feature_id)}
              />
            ))}
          </svg>
        </div>

        <aside style={{ border: "1px solid #4c493f", borderRadius: "8px", padding: "16px", background: "#1d1d18" }}>
          <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Structure</h2>
          {selected?.structure ? (
            <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "8px 12px", margin: 0 }}>
              <dt>Name</dt><dd style={{ margin: 0 }}>{selected.structure.display_name}</dd>
              <dt>Type</dt><dd style={{ margin: 0 }}>{selected.structure.definition_id.replaceAll("_", " ")}</dd>
              <dt>Status</dt><dd style={{ margin: 0 }}>{selected.structure.status}</dd>
              <dt>Since</dt><dd style={{ margin: 0 }}>Year {selected.structure.established_year}</dd>
              <dt>Authority</dt><dd style={{ margin: 0 }}>Authoritative #60 structure</dd>
            </dl>
          ) : (
            <p style={{ opacity: 0.7 }}>Hover or select an outlined strategic structure. Ordinary houses, tents, gardens and streets are visual fabric only.</p>
          )}

          {result.issues.length > 0 && (
            <div style={{ marginTop: "20px", borderTop: "1px solid #4c493f", paddingTop: "14px" }}>
              <h2 style={{ fontSize: "1rem" }}>Generation notes</h2>
              <ul style={{ paddingLeft: "20px", marginBottom: 0 }}>
                {result.issues.map((issue, index) => <li key={`${issue.code}:${issue.structure_id ?? index}`}>{issue.message}</li>)}
              </ul>
            </div>
          )}

          <p style={{ marginTop: "20px", fontSize: "0.78rem", opacity: 0.55, wordBreak: "break-all" }}>
            World {worldId}<br />
            {result.generation_version} · {result.renderer_version}
          </p>
        </aside>
      </section>
    </main>
  );
}

function MapFeatureShape({
  feature,
  active,
  interactive = false,
  onEnter,
  onLeave,
  onSelect,
}: {
  feature: LocalMapFeature;
  active: boolean;
  interactive?: boolean;
  onEnter?: () => void;
  onLeave?: () => void;
  onSelect?: () => void;
}) {
  const style = featureStyle(feature, active, interactive);
  const common = {
    style,
    onMouseEnter: onEnter,
    onMouseLeave: onLeave,
    onClick: onSelect,
    tabIndex: interactive ? 0 : undefined,
    role: interactive ? "button" : undefined,
    onKeyDown: interactive ? (event: React.KeyboardEvent<SVGElement>) => {
      if (event.key === "Enter" || event.key === " ") onSelect?.();
    } : undefined,
  };
  const geometry = feature.geometry;
  if (geometry.type === "Point") {
    return <circle {...common} cx={geometry.coordinates[0]} cy={geometry.coordinates[1]} r={interactive ? 4.5 : 2.8}><title>{featureLabel(feature)}</title></circle>;
  }
  if (geometry.type === "LineString") {
    return <polyline {...common} fill="none" points={geometry.coordinates.map(pointText).join(" ")}><title>{featureLabel(feature)}</title></polyline>;
  }
  if (geometry.type === "Polygon") {
    return <g>{geometry.coordinates.map((ring, index) => <polygon key={index} {...common} points={ring.map(pointText).join(" ")}><title>{featureLabel(feature)}</title></polygon>)}</g>;
  }
  return <g>{geometry.coordinates.flatMap((polygon, polygonIndex) => polygon.map((ring, ringIndex) => (
    <polygon key={`${polygonIndex}:${ringIndex}`} {...common} points={ring.map(pointText).join(" ")}><title>{featureLabel(feature)}</title></polygon>
  )))}</g>;
}

function featureStyle(feature: LocalMapFeature, active: boolean, interactive: boolean): React.CSSProperties {
  if (feature.authority === "authoritative_structure") {
    return {
      fill: active ? "#d0a85f" : "#b99150",
      stroke: "#30281c",
      strokeWidth: active ? 3.5 : 2.5,
      cursor: interactive ? "pointer" : "default",
      vectorEffect: "non-scaling-stroke",
    };
  }
  if (feature.authority === "natural_context") {
    return { fill: "#a8c6ca", stroke: "#779ba1", strokeWidth: 1.8, opacity: 0.8, vectorEffect: "non-scaling-stroke" };
  }
  if (feature.authority === "generated_infrastructure_geometry") {
    return { fill: "none", stroke: "#897b65", strokeWidth: 1.3, opacity: 0.8, vectorEffect: "non-scaling-stroke" };
  }
  return { fill: "#d4c4a5", stroke: "#8e826d", strokeWidth: 0.7, opacity: 0.82, vectorEffect: "non-scaling-stroke" };
}

function featureLabel(feature: LocalMapFeature): string {
  if (feature.structure) return `${feature.structure.display_name} · ${feature.structure.status}`;
  const kind = feature.properties.kind ?? feature.properties.wardType ?? feature.source_layer;
  return `${String(kind).replaceAll("_", " ")} · visual only`;
}

function pointText(point: LocalPoint): string {
  return `${point[0]},${point[1]}`;
}
