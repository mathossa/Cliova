import { assetPaths } from "./command-center.data";
import type { WorldSnapshot } from "./command-center.types";

export function RegionOverview({ region, selectedLabel }: { region: WorldSnapshot["selectedRegion"]; selectedLabel: string }) {
  return (
      <section className="panel region-panel">
        <div className="panel-heading compact">
          <div>
            <span className="eyebrow">Selected context</span>
            <h2>{selectedLabel}</h2>
          </div>
          <span className="placeholder-badge">mock data</span>
        </div>
        {region ? <>
        <div className="region-summary">
          <div
            className="region-image"
            role="img"
            aria-label="Region artwork placeholder"
            style={{
              backgroundImage: `linear-gradient(180deg, rgba(8, 14, 19, .08), rgba(8, 14, 19, .2)), url(${assetPaths.regionPreview})`,
            }}
          >
            <span>asset placeholder</span>
          </div>
          <p>{region.description}</p>
        </div>
        <dl className="region-stats">
          <div><dt>Population</dt><dd>{region.population}</dd></div>
          <div><dt>Primary resource</dt><dd>{region.primaryResource}</dd></div>
          <div><dt>Administration</dt><dd>{region.administration}</dd></div>
          <div><dt>Stability</dt><dd>{region.stability}</dd></div>
          <div><dt>Conditions</dt><dd>{region.conditions}</dd></div>
        </dl>
        </> : <p className="module-description">No region details available for this selection.</p>}
      </section>
  );
}
