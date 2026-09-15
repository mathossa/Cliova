"use client";

import Link from "next/link";
import { useMemo, useRef, useState } from "react";

import type { LocalMapFeature, LocalMapResult, LocalPoint } from "./local-map-generator";

type MapCamera = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type PanStart = {
  pointerId: number;
  clientX: number;
  clientY: number;
  camera: MapCamera;
};

const MIN_ZOOM = 0.75;
const MAX_ZOOM = 8;
const SETTLEMENT_FOCUS_LAYERS = new Set([
  "building",
  "street",
  "wall",
  "tower",
  "entrance",
  "gate",
  "crossing",
  "junction",
  "pier",
  "poi",
]);

export function LocalMapView({ result, worldId, settlementName }: {
  result: LocalMapResult;
  worldId: string;
  settlementName: string;
}) {
  const baseCamera = useMemo(() => initialCamera(result), [result]);
  const [camera, setCamera] = useState<MapCamera>(baseCamera);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef<PanStart | null>(null);
  const selected = useMemo(
    () => result.features.find((feature) => feature.feature_id === selectedId) ?? null,
    [result.features, selectedId],
  );
  const mapped = result.structure_feature_mappings.filter((item) => item.status === "mapped").length;
  const zoom = baseCamera.width / camera.width;
  const viewBox = `${camera.x} ${camera.y} ${camera.width} ${camera.height}`;

  const zoomBy = (factor: number, anchor?: LocalPoint) => {
    setCamera((current) => zoomCamera(current, baseCamera, factor, anchor));
  };

  const handleWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const anchor = clientToMapPoint(event.currentTarget, event.clientX, event.clientY);
    zoomBy(event.deltaY < 0 ? 1.18 : 1 / 1.18, anchor ?? undefined);
  };

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    panStart.current = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      camera,
    };
    setIsPanning(true);
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const start = panStart.current;
    if (start === null || start.pointerId !== event.pointerId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const dx = (event.clientX - start.clientX) * (start.camera.width / rect.width);
    const dy = (event.clientY - start.clientY) * (start.camera.height / rect.height);
    setCamera({
      ...start.camera,
      x: start.camera.x - dx,
      y: start.camera.y - dy,
    });
  };

  const finishPan = (event: React.PointerEvent<SVGSVGElement>) => {
    if (panStart.current?.pointerId === event.pointerId) {
      panStart.current = null;
      setIsPanning(false);
    }
  };

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
          <button type="button" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.25)}>−</button>
          <button type="button" aria-label="Fit map" title="Fit map" onClick={() => setCamera(baseCamera)}>
            {Math.round(zoom * 100)}%
          </button>
          <button type="button" aria-label="Zoom in" onClick={() => zoomBy(1.25)}>+</button>
        </div>
      </header>

      <section style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(240px, 320px)", gap: "16px", alignItems: "start" }}>
        <div
          aria-label={`Map of ${settlementName}`}
          style={{
            position: "relative",
            overflow: "hidden",
            height: "clamp(480px, 72vh, 900px)",
            border: "1px solid #4c493f",
            background: "#e8dfca",
            borderRadius: "8px",
          }}
        >
          <svg
            viewBox={viewBox}
            role="img"
            aria-label={`${settlementName} local settlement geometry`}
            onWheel={handleWheel}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={finishPan}
            onPointerCancel={finishPan}
            style={{
              display: "block",
              width: "100%",
              height: "100%",
              cursor: isPanning ? "grabbing" : "grab",
              touchAction: "none",
              userSelect: "none",
            }}
          >
            <defs>
              <pattern id="local-map-paper" width="18" height="18" patternUnits="userSpaceOnUse">
                <circle cx="3" cy="4" r="0.55" fill="#8a7d63" opacity="0.14" />
                <circle cx="13" cy="12" r="0.4" fill="#8a7d63" opacity="0.1" />
              </pattern>
            </defs>
            <rect
              x={result.bounds.min_x - 250}
              y={result.bounds.min_y - 250}
              width={result.bounds.max_x - result.bounds.min_x + 500}
              height={result.bounds.max_y - result.bounds.min_y + 500}
              fill="#e8dfca"
            />
            <rect
              x={result.bounds.min_x - 250}
              y={result.bounds.min_y - 250}
              width={result.bounds.max_x - result.bounds.min_x + 500}
              height={result.bounds.max_y - result.bounds.min_y + 500}
              fill="url(#local-map-paper)"
            />
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
          <div
            style={{
              position: "absolute",
              left: "12px",
              bottom: "10px",
              padding: "6px 9px",
              borderRadius: "6px",
              background: "rgba(30, 28, 23, 0.76)",
              color: "#eee9dc",
              fontSize: "0.72rem",
              pointerEvents: "none",
            }}
          >
            Wheel to zoom · drag to pan · select outlined structures
          </div>
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

          <div style={{ marginTop: "20px", borderTop: "1px solid #4c493f", paddingTop: "14px" }}>
            <h2 style={{ margin: "0 0 10px", fontSize: "1rem" }}>Map key</h2>
            <MapKeyRow swatch={{ background: "#cda45c", border: "2px solid #30281c" }} label="Authoritative structure" />
            <MapKeyRow swatch={{ background: "#c4aa79", border: "1px solid #6f5d40" }} label="Buildings / shelters" />
            <MapKeyRow swatch={{ background: "#d8ccaa", border: "1px solid #b7aa84" }} label="Fields / visual fabric" />
            <MapKeyRow swatch={{ background: "#87745a", height: "3px", marginTop: "5px" }} label="Roads / paths" />
          </div>

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

function MapKeyRow({ swatch, label }: { swatch: React.CSSProperties; label: string }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "22px 1fr", gap: "8px", alignItems: "center", marginTop: "7px", fontSize: "0.82rem", opacity: 0.82 }}>
      <span aria-hidden="true" style={{ display: "block", width: "18px", height: "12px", borderRadius: "2px", ...swatch }} />
      <span>{label}</span>
    </div>
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
  const interactionProps = {
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
    if (feature.properties.kind === "hearth") {
      const [cx, cy] = geometry.coordinates;
      return (
        <g {...interactionProps}>
          <circle cx={cx} cy={cy} r={6.5} fill="#7b6445" opacity="0.2" />
          <circle cx={cx} cy={cy} r={4.3} fill="#b86139" stroke="#57402b" strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
          <circle cx={cx} cy={cy - 0.6} r={1.7} fill="#e1b65e" />
          <title>{featureLabel(feature)}</title>
        </g>
      );
    }
    return <circle {...interactionProps} style={style} cx={geometry.coordinates[0]} cy={geometry.coordinates[1]} r={interactive ? 4.5 : 2.8}><title>{featureLabel(feature)}</title></circle>;
  }

  if (geometry.type === "LineString") {
    return <polyline {...interactionProps} style={style} fill="none" points={geometry.coordinates.map(pointText).join(" ")}><title>{featureLabel(feature)}</title></polyline>;
  }

  if (geometry.type === "Polygon") {
    if (feature.properties.kind === "tent" && geometry.coordinates[0]?.length >= 3) {
      const ring = geometry.coordinates[0];
      const apex = ring[0];
      const left = ring[1];
      const right = ring[2];
      const baseMid: LocalPoint = [(left[0] + right[0]) / 2, (left[1] + right[1]) / 2];
      return (
        <g {...interactionProps}>
          <polygon style={style} points={ring.map(pointText).join(" ")} />
          <line
            x1={apex[0]}
            y1={apex[1]}
            x2={baseMid[0]}
            y2={baseMid[1]}
            stroke="#72583a"
            strokeWidth={0.9}
            opacity={0.7}
            vectorEffect="non-scaling-stroke"
          />
          <title>{featureLabel(feature)}</title>
        </g>
      );
    }
    return (
      <g {...interactionProps}>
        {geometry.coordinates.map((ring, index) => (
          <polygon key={index} style={style} points={ring.map(pointText).join(" ")} />
        ))}
        <title>{featureLabel(feature)}</title>
      </g>
    );
  }

  return (
    <g {...interactionProps}>
      {geometry.coordinates.flatMap((polygon, polygonIndex) => polygon.map((ring, ringIndex) => (
        <polygon key={`${polygonIndex}:${ringIndex}`} style={style} points={ring.map(pointText).join(" ")} />
      )))}
      <title>{featureLabel(feature)}</title>
    </g>
  );
}

function featureStyle(feature: LocalMapFeature, active: boolean, interactive: boolean): React.CSSProperties {
  if (feature.authority === "authoritative_structure") {
    return {
      fill: active ? "#deb766" : "#cda45c",
      stroke: "#30281c",
      strokeWidth: active ? 3.5 : 2.5,
      cursor: interactive ? "pointer" : "default",
      vectorEffect: "non-scaling-stroke",
    };
  }

  if (feature.authority === "natural_context") {
    if (feature.geometry.type === "LineString") {
      return { fill: "none", stroke: "#6f9da5", strokeWidth: 3, opacity: 0.85, vectorEffect: "non-scaling-stroke" };
    }
    return { fill: "#a8c6ca", stroke: "#779ba1", strokeWidth: 1.8, opacity: 0.72, vectorEffect: "non-scaling-stroke" };
  }

  if (feature.authority === "generated_infrastructure_geometry") {
    const isCampPath = feature.source_layer === "path";
    return {
      fill: "none",
      stroke: isCampPath ? "#8b7657" : "#76664f",
      strokeWidth: isCampPath ? 1.8 : 1.45,
      strokeDasharray: isCampPath ? "5 3" : undefined,
      opacity: isCampPath ? 0.72 : 0.9,
      vectorEffect: "non-scaling-stroke",
    };
  }

  switch (feature.source_layer) {
    case "building":
      return { fill: "#c4aa79", stroke: "#6f5d40", strokeWidth: 0.9, opacity: 0.96, vectorEffect: "non-scaling-stroke" };
    case "shelter":
      return { fill: "#c79d62", stroke: "#655038", strokeWidth: 1.15, opacity: 0.95, vectorEffect: "non-scaling-stroke" };
    case "field":
      return { fill: "#d8ccaa", stroke: "#b7aa84", strokeWidth: 0.7, opacity: 0.32, vectorEffect: "non-scaling-stroke" };
    case "green":
      return { fill: "#bdc5a3", stroke: "#87906f", strokeWidth: 0.7, opacity: 0.64, vectorEffect: "non-scaling-stroke" };
    case "ward":
      return { fill: "#e3d7bc", stroke: "#b9ac90", strokeWidth: 0.65, opacity: 0.38, vectorEffect: "non-scaling-stroke" };
    case "poi":
      return { fill: "#b8945e", stroke: "#665238", strokeWidth: 1, opacity: 0.88, vectorEffect: "non-scaling-stroke" };
    default:
      return { fill: "#d4c4a5", stroke: "#8e826d", strokeWidth: 0.7, opacity: 0.7, vectorEffect: "non-scaling-stroke" };
  }
}

function initialCamera(result: LocalMapResult): MapCamera {
  const focusFeatures = result.renderer === "settlemaker"
    ? result.features.filter(
      (feature) => feature.authority === "authoritative_structure" || SETTLEMENT_FOCUS_LAYERS.has(feature.source_layer),
    )
    : result.features;
  const bounds = boundsForFeatures(focusFeatures.length > 0 ? focusFeatures : result.features, result);
  const width = Math.max(1, bounds.max_x - bounds.min_x);
  const height = Math.max(1, bounds.max_y - bounds.min_y);
  const padding = Math.max(10, Math.max(width, height) * 0.13);
  return {
    x: bounds.min_x - padding,
    y: bounds.min_y - padding,
    width: width + padding * 2,
    height: height + padding * 2,
  };
}

function boundsForFeatures(features: LocalMapFeature[], result: LocalMapResult) {
  const points = features.flatMap(featurePoints);
  if (points.length === 0) return result.bounds;
  return {
    min_x: Math.min(...points.map((point) => point[0])),
    min_y: Math.min(...points.map((point) => point[1])),
    max_x: Math.max(...points.map((point) => point[0])),
    max_y: Math.max(...points.map((point) => point[1])),
  };
}

function featurePoints(feature: LocalMapFeature): LocalPoint[] {
  const geometry = feature.geometry;
  if (geometry.type === "Point") return [geometry.coordinates];
  if (geometry.type === "LineString") return geometry.coordinates;
  if (geometry.type === "Polygon") return geometry.coordinates.flat();
  return geometry.coordinates.flat(2) as LocalPoint[];
}

function zoomCamera(current: MapCamera, base: MapCamera, factor: number, anchor?: LocalPoint): MapCamera {
  const currentZoom = base.width / current.width;
  const nextZoom = clamp(currentZoom * factor, MIN_ZOOM, MAX_ZOOM);
  if (Math.abs(nextZoom - currentZoom) < 0.0001) return current;

  const nextWidth = base.width / nextZoom;
  const nextHeight = base.height / nextZoom;
  const [anchorX, anchorY] = anchor ?? [current.x + current.width / 2, current.y + current.height / 2];
  const ratioX = (anchorX - current.x) / current.width;
  const ratioY = (anchorY - current.y) / current.height;
  return {
    x: anchorX - nextWidth * ratioX,
    y: anchorY - nextHeight * ratioY,
    width: nextWidth,
    height: nextHeight,
  };
}

function clientToMapPoint(svg: SVGSVGElement, clientX: number, clientY: number): LocalPoint | null {
  const matrix = svg.getScreenCTM();
  if (matrix === null) return null;
  const point = svg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  const mapped = point.matrixTransform(matrix.inverse());
  return [mapped.x, mapped.y];
}

function featureLabel(feature: LocalMapFeature): string {
  if (feature.structure) return `${feature.structure.display_name} · ${feature.structure.status}`;
  const kind = feature.properties.kind ?? feature.properties.wardType ?? feature.source_layer;
  return `${String(kind).replaceAll("_", " ")} · visual only`;
}

function pointText(point: LocalPoint): string {
  return `${point[0]},${point[1]}`;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
