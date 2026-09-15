CREATE TABLE cliova_worlds (
    world_id uuid PRIMARY KEY,
    seed text NOT NULL,
    current_tick bigint NOT NULL CHECK (current_tick >= 0),
    current_year bigint NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version > 0),
    simulation_version integer NOT NULL CHECK (simulation_version > 0),
    rng_algorithm text NOT NULL,
    payload_schema_version integer NOT NULL CHECK (payload_schema_version > 0),
    state_json jsonb NOT NULL CHECK (jsonb_typeof(state_json) = 'object')
);

CREATE TABLE cliova_world_snapshots (
    world_id uuid NOT NULL REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    tick bigint NOT NULL CHECK (tick >= 0),
    year bigint NOT NULL,
    seed text NOT NULL,
    schema_version integer NOT NULL CHECK (schema_version > 0),
    simulation_version integer NOT NULL CHECK (simulation_version > 0),
    rng_algorithm text NOT NULL,
    payload_schema_version integer NOT NULL CHECK (payload_schema_version > 0),
    state_json jsonb NOT NULL CHECK (jsonb_typeof(state_json) = 'object'),
    PRIMARY KEY (world_id, tick)
);

CREATE TABLE cliova_queued_inputs (
    queue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    submitted_tick bigint NOT NULL CHECK (submitted_tick > 0),
    consumed_tick bigint NULL CHECK (consumed_tick IS NULL OR consumed_tick >= submitted_tick),
    payload_schema_version integer NOT NULL CHECK (payload_schema_version > 0),
    input_json jsonb NOT NULL CHECK (jsonb_typeof(input_json) = 'object')
);

CREATE INDEX cliova_queued_inputs_pending_order_idx
    ON cliova_queued_inputs (world_id, submitted_tick, queue_id)
    WHERE consumed_tick IS NULL;

CREATE TABLE cliova_completed_ticks (
    world_id uuid NOT NULL REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    tick bigint NOT NULL CHECK (tick > 0),
    year bigint NOT NULL,
    previous_tick bigint NOT NULL CHECK (previous_tick >= 0),
    input_count integer NOT NULL CHECK (input_count >= 0),
    event_count integer NOT NULL CHECK (event_count >= 0),
    schema_version integer NOT NULL CHECK (schema_version > 0),
    simulation_version integer NOT NULL CHECK (simulation_version > 0),
    state_sha256 char(64) NOT NULL,
    PRIMARY KEY (world_id, tick),
    CHECK (tick = previous_tick + 1)
);

CREATE TABLE cliova_history_events (
    world_id uuid NOT NULL REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    event_id uuid NOT NULL,
    tick bigint NOT NULL CHECK (tick > 0),
    year bigint NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    source text NOT NULL,
    kind text NOT NULL,
    payload_schema_version integer NOT NULL CHECK (payload_schema_version > 0),
    event_json jsonb NOT NULL CHECK (jsonb_typeof(event_json) = 'object'),
    PRIMARY KEY (world_id, event_id),
    UNIQUE (world_id, tick, ordinal)
);

CREATE INDEX cliova_history_events_world_tick_idx
    ON cliova_history_events (world_id, tick, ordinal);

CREATE INDEX cliova_history_events_world_kind_idx
    ON cliova_history_events (world_id, kind, tick, ordinal);

CREATE TABLE cliova_history_event_causes (
    world_id uuid NOT NULL,
    event_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    cause_event_id uuid NOT NULL,
    PRIMARY KEY (world_id, event_id, ordinal),
    FOREIGN KEY (world_id, event_id)
        REFERENCES cliova_history_events(world_id, event_id)
        ON DELETE CASCADE
);

CREATE INDEX cliova_history_event_causes_target_idx
    ON cliova_history_event_causes (world_id, cause_event_id);
