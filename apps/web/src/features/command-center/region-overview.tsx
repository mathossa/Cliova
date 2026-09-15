import { assetPaths } from "./command-center.data";
import type { RegionView } from "./command-center.types";

export function RegionOverview({
  regions,
  selectedId,
  onSelect,
}: {
  regions: RegionView[];
  selectedId: string;
  onSelect: (regionId: string) => void;
}) {
  const region = regions.find((item) => item.id === selectedId) ?? regions[0] ?? null;

  return (
    <section className="panel region-panel">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">Selected region</span>
          <h2>{region?.label ?? "No region available"}</h2>
        </div>
        <span className="live-badge">live</span>
      </div>

      {region ? (
        <>
          {regions.length > 1 && (
            <label className="region-picker">
              Region
              <select value={region.id} onChange={(event) => onSelect(event.target.value)}>
                {regions.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </label>
          )}
          <div className="region-summary">
            <div
              className="region-image"
              role="img"
              aria-label="Presentation-only region artwork"
              style={{
                backgroundImage: `linear-gradient(180deg, rgba(8, 14, 19, .08), rgba(8, 14, 19, .2)), url(${assetPaths.regionPreview})`,
              }}
            >
              <span>presentation artwork</span>
            </div>
            <p>
              {region.terrain} terrain · {region.biome} biome. The artwork is illustrative; all values shown below come from API v1.
            </p>
          </div>
          <dl className="region-stats">
            <Stat label="Population" value={region.population} />
            <Stat label="Terrain" value={region.terrain} />
            <Stat label="Biome" value={region.biome} />
            <Stat label="Habitability" value={region.habitability} />
            <Stat label="Water access" value={region.waterAccess} />
            <Stat label="Climate pressure" value={region.climatePressure} />
            <Stat label="Food security" value={region.food.foodSecurity} />
            <Stat label="Food shortage" value={region.food.shortageSeverity} />
          </dl>
        </>
      ) : (
        <p className="module-description">No authoritative region data is available for this world.</p>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}
