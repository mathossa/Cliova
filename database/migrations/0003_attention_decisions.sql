CREATE TABLE cliova_attention_items (
    attention_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    target_kind text NULL CHECK (target_kind IS NULL OR target_kind IN ('society', 'polity')),
    target_id uuid NULL,
    created_tick integer NOT NULL CHECK (created_tick >= 0),
    created_year integer NOT NULL,
    category text NOT NULL,
    priority text NOT NULL CHECK (priority IN ('informational', 'important', 'urgent')),
    context text NOT NULL,
    related_event_ids uuid[] NOT NULL DEFAULT '{}',
    related_subjects jsonb NOT NULL DEFAULT '[]'::jsonb,
    CHECK ((target_kind IS NULL) = (target_id IS NULL)),
    UNIQUE (world_id, category, target_kind, target_id, related_event_ids)
);

CREATE INDEX cliova_attention_items_world_tick_idx
    ON cliova_attention_items (world_id, created_tick DESC, attention_id);

CREATE TABLE cliova_decision_opportunities (
    opportunity_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    target_kind text NOT NULL CHECK (target_kind IN ('society', 'polity')),
    target_id uuid NOT NULL,
    created_tick integer NOT NULL CHECK (created_tick >= 0),
    created_year integer NOT NULL,
    category text NOT NULL,
    context text NOT NULL,
    related_event_ids uuid[] NOT NULL DEFAULT '{}',
    related_subjects jsonb NOT NULL DEFAULT '[]'::jsonb,
    earliest_effect_tick integer NOT NULL CHECK (earliest_effect_tick >= 0),
    expires_at_tick integer NULL CHECK (expires_at_tick IS NULL OR expires_at_tick >= 0),
    default_behavior text NOT NULL,
    response_intent text NOT NULL,
    status text NOT NULL CHECK (status IN ('open', 'responded', 'expired')),
    response_queue_id bigint NULL REFERENCES cliova_queued_inputs(queue_id),
    response_submitted_tick integer NULL CHECK (response_submitted_tick IS NULL OR response_submitted_tick >= 0),
    response_directive_id uuid NULL,
    CHECK (expires_at_tick IS NULL OR expires_at_tick >= earliest_effect_tick),
    CHECK ((status = 'open' AND response_queue_id IS NULL AND response_submitted_tick IS NULL AND response_directive_id IS NULL)
        OR status IN ('responded', 'expired')),
    UNIQUE (world_id, category, target_kind, target_id, related_event_ids)
);

CREATE INDEX cliova_decision_opportunities_world_status_idx
    ON cliova_decision_opportunities (world_id, status, created_tick DESC, opportunity_id);
