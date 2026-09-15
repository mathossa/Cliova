import type { HistoryFeedItem } from "./command-center.types";

export function HistoryFeed({ feed }: { feed: HistoryFeedItem[] }) {
  return (
    <section className="panel feed-panel">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">World history</span>
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
                {item.causeCount > 0 ? `${item.causeCount} causal link${item.causeCount === 1 ? "" : "s"}` : "Recorded event"}
              </small>
              <details className="feed-technical">
                <summary>Technical details</summary>
                <div><strong>Source:</strong> {item.source}</div>
                <div>{item.technicalDetail}</div>
              </details>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
