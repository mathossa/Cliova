import type { HistoryFeedItem } from "./command-center.types";

export function HistoryFeed({ feed }: { feed: HistoryFeedItem[] }) {
  return (
    <section className="panel feed-panel">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">Authoritative history</span>
          <h2>Recent activity</h2>
        </div>
        <span className="live-badge">live</span>
      </div>
      <div className="feed-list">
        {feed.length === 0 && <p className="empty-copy">No historical activity recorded for the recent tick window.</p>}
        {feed.map((item) => (
          <div className="feed-line" key={item.id} data-event-id={item.id}>
            <time>[{item.time}]</time>
            <div>
              <span className={`tone-${item.tone}`}>{item.text}</span>
              <small className="feed-meta">
                {item.source}{item.causeCount > 0 ? ` · ${item.causeCount} causal link${item.causeCount === 1 ? "" : "s"}` : ""}
              </small>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
