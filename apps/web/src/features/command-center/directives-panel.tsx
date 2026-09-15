"use client";

import { FormEvent, useMemo, useState } from "react";
import { describeApiError, type DirectivePriority, type DirectiveSubmissionRequest } from "../../lib/api";
import type { WorldSnapshot } from "./command-center.types";

const priorities: DirectivePriority[] = ["low", "normal", "high"];

export function DirectivesPanel({
  world,
  onSubmit,
}: {
  world: WorldSnapshot;
  onSubmit: (request: DirectiveSubmissionRequest) => Promise<void>;
}) {
  const validTargets = useMemo(
    () => world.societies.filter((society) => society.kind === "society" || society.kind === "polity"),
    [world.societies],
  );
  const [author, setAuthor] = useState("command-center");
  const [targetId, setTargetId] = useState("");
  const [priority, setPriority] = useState<DirectivePriority>("normal");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedTarget = validTargets.find((society) => society.id === targetId) ?? validTargets[0] ?? null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTarget || selectedTarget.kind === "unsupported") {
      setError("No valid society or polity target is available for directives.");
      return;
    }

    setSubmitting(true);
    setFeedback(null);
    setError(null);
    try {
      await onSubmit({
        author: author.trim(),
        target: { kind: selectedTarget.kind, id: selectedTarget.id },
        intent: "strengthen_food_reserves",
        priority,
      });
      setFeedback("Directive queued. Its authoritative lifecycle will update after refresh or a later tick.");
    } catch (submissionError) {
      setError(describeApiError(submissionError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="directive-workspace">
      <section className="panel directive-submit-panel">
        <div className="panel-heading compact">
          <div>
            <span className="eyebrow">Authoritative input</span>
            <h2>Submit directive</h2>
          </div>
          <span className="live-badge">API v1</span>
        </div>
        <form className="directive-form" onSubmit={submit}>
          <label>
            Author
            <input required maxLength={100} value={author} onChange={(event) => setAuthor(event.target.value)} />
          </label>
          <label>
            Target
            <select
              value={selectedTarget?.id ?? ""}
              onChange={(event) => setTargetId(event.target.value)}
              disabled={validTargets.length === 0}
            >
              {validTargets.length === 0 && <option value="">No supported targets</option>}
              {validTargets.map((society) => (
                <option key={society.id} value={society.id}>{society.label}</option>
              ))}
            </select>
          </label>
          <label>
            Intent
            <input value="Strengthen food reserves" readOnly aria-label="Directive intent" />
          </label>
          <label>
            Priority
            <select value={priority} onChange={(event) => setPriority(event.target.value as DirectivePriority)}>
              {priorities.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <button type="submit" disabled={submitting || validTargets.length === 0 || author.trim().length === 0}>
            {submitting ? "Submitting…" : "Queue directive"}
          </button>
        </form>
        {feedback && <p className="action-success" role="status">{feedback}</p>}
        {error && <p className="action-error" role="alert">{error}</p>}
      </section>

      <section className="panel directive-list-panel">
        <div className="panel-heading compact">
          <div>
            <span className="eyebrow">Directive lifecycle</span>
            <h2>Queue and status</h2>
          </div>
        </div>
        <div className="directive-groups">
          <div>
            <h3>Pending queue</h3>
            {world.pendingDirectives.length === 0 ? (
              <p className="empty-copy">No pending directives.</p>
            ) : (
              <ul className="live-list">
                {world.pendingDirectives.map((directive) => (
                  <li key={directive.queueId}>
                    <strong>{directive.intent}</strong>
                    <span>queued · {directive.priority} · tick {directive.submittedTick}</span>
                    <small>{directive.author} → {shortId(directive.targetId)}</small>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3>Authoritative directives</h3>
            {world.directives.length === 0 ? (
              <p className="empty-copy">No authoritative directive lifecycle records yet.</p>
            ) : (
              <ul className="live-list">
                {world.directives.map((directive) => (
                  <li key={directive.id} data-directive-id={directive.id}>
                    <strong>{directive.intent}</strong>
                    <span>{directive.status} · progress {directive.progress} · {directive.priority}</span>
                    <small>{directive.author} → {shortId(directive.targetId)} · submitted tick {directive.submittedTick}</small>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function shortId(value: string): string {
  return value.slice(0, 8);
}
