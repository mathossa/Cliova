import type { WorldSnapshot } from "./command-center.types";

export function HistoryFeed({ feed }: { feed: WorldSnapshot["feed"] }) {
  return (
      <section className="panel feed-panel">
        <div className="panel-heading compact">
          <div>
            <span className="eyebrow">Terminal / intel</span>
            <h2>World feed</h2>
          </div>
          <div className="feed-filters" aria-label="Feed filters placeholders">
            <button type="button" disabled className="selected">All</button>
            <button type="button" disabled>State</button>
            <button type="button" disabled>Economy</button>
            <button type="button" disabled>Events</button>
          </div>
        </div>
        <div className="feed-list">
          {feed.length === 0 && <p>No historical activity available.</p>}
          {feed.map((item) => (
            <div className="feed-line" key={`${item.time}-${item.text}`}>
              <time>[{item.time}]</time>
              <span className={`tone-${item.tone}`}>{item.text}</span>
            </div>
          ))}
        </div>
      </section>
  );
}
