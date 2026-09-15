"use client";

import { FormEvent, useMemo, useState } from "react";
import {
  describeApiError,
  type DirectiveIntent,
  type DirectivePriority,
  type DirectiveSubmissionRequest,
} from "../../lib/api";
import type { WorldSnapshot } from "./command-center.types";

const DEVELOPMENT_AUTHOR = "development-operator";
const priorities: DirectivePriority[] = ["low", "normal", "high"];
const directiveActions: Array<{ intent: DirectiveIntent; label: string; description: string }> = [
  {
    intent: "strengthen_food_reserves",
    label: "Strengthen food reserves",
    description: "Prioritize improving and maintaining food reserves. The simulation determines what can actually be achieved.",
  },
];

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
  const [targetId, setTargetId] = useState("");
  const [intent, setIntent] = useState<DirectiveIntent>(directiveActions[0]!.intent);
  const [priority, setPriority] = useState<DirectivePriority>("normal");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedTarget = validTargets.find((society) => society.id === targetId) ?? validTargets[0] ?? null;
  const selectedAction = directiveActions.find((action) => action.intent === intent) ?? directiveActions[0]!;

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
        author: DEVELOPMENT_AUTHOR,
        target: { kind: selectedTarget.kind, id: selectedTarget.id },
        intent,
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
            <span className="eyebrow">Development operator · authoritative input</span>
            <h2>Issue directive</h2>
          </div>
          <span className="live-badge">API v1</span>
        </div>
        <div className="directive-context">
          You are acting as the development operator with world-wide access. You are not currently assigned to a single society.
        </div>
        <form className="directive-form" onSubmit={submit}>
          <label>
            Target society
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
            {selectedTarget && <small>Home region: {selectedTarget.regionLabel} · ID {shortId(selectedTarget.id)}</small>}
          </label>
          <label>
            Action
            <select value={intent} onChange={(event) => setIntent(event.target.value as DirectiveIntent)}>
              {directiveActions.map((action) => (
                <option key={action.intent} value={action.intent}>{action.label}</option>
              ))}
            </select>
            <small>{selectedAction.description}</small>
          </label>
          <label>
            Priority
            <select value={priority} onChange={(event) => setPriority(event.target.value as DirectivePriority)}>
              {priorities.map((item) => <option key={item} value={item}>{capitalize(item)}</option>)}
            </select>
            <small>Priority is part of the directive request; it does not guarantee successful execution.</small>
          </label>
          <div className="directive-submit-summary">
            <span className="eyebrow">Available actions</span>
            <p>API v1 currently exposes one controlled directive action. Free text is not interpreted as simulation input.</p>
          </div>
          <button type="submit" disabled={submitting || validTargets.length === 0}>
            {submitting ? "Submitting…" : "Issue directive"}
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
                    <span>Queued · {capitalize(directive.priority)} priority · tick {directive.submittedTick}</span>
                    <small>{formatAuthor(directive.author)} → {directive.targetLabel}</small>
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
                    <span>{capitalize(directive.status)} · progress {directive.progress} · {capitalize(directive.priority)} priority</span>
                    <small>{formatAuthor(directive.author)} → {directive.targetLabel} · submitted tick {directive.submittedTick}</small>
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

function formatAuthor(author: string): string {
  if (author === DEVELOPMENT_AUTHOR || author === "command-center") return "Development operator";
  return author;
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function shortId(value: string): string {
  return value.slice(0, 8);
}
