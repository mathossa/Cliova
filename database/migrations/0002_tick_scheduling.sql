CREATE TABLE cliova_tick_runs (
    run_id uuid PRIMARY KEY,
    world_id uuid NOT NULL REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    target_tick bigint NOT NULL CHECK (target_tick > 0),
    trigger text NOT NULL CHECK (trigger IN ('scheduled', 'manual')),
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    scheduled_for timestamptz NULL,
    claim_token uuid NOT NULL,
    claim_expires_at timestamptz NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz NULL,
    failed_at timestamptz NULL,
    failure_reason text NULL,
    accepted_input_max_queue_id bigint NULL,
    accepted_input_count integer NOT NULL DEFAULT 0 CHECK (accepted_input_count >= 0),
    attempt_count integer NOT NULL DEFAULT 1 CHECK (attempt_count > 0),
    UNIQUE (world_id, target_tick),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
    CHECK ((status = 'failed') = (failed_at IS NOT NULL))
);

CREATE INDEX cliova_tick_runs_world_status_idx
    ON cliova_tick_runs (world_id, status, target_tick);

CREATE TABLE cliova_world_schedules (
    world_id uuid PRIMARY KEY REFERENCES cliova_worlds(world_id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused')),
    next_eligible_at timestamptz NULL,
    current_run_id uuid NULL REFERENCES cliova_tick_runs(run_id) ON DELETE SET NULL,
    last_completed_run_id uuid NULL REFERENCES cliova_tick_runs(run_id) ON DELETE SET NULL,
    last_completed_at timestamptz NULL,
    last_failure_at timestamptz NULL,
    last_failure_reason text NULL,
    duplicate_attempt_count integer NOT NULL DEFAULT 0 CHECK (duplicate_attempt_count >= 0)
);

CREATE INDEX cliova_world_schedules_due_idx
    ON cliova_world_schedules (status, next_eligible_at)
    WHERE status = 'active';

INSERT INTO cliova_world_schedules (world_id)
SELECT world_id FROM cliova_worlds
ON CONFLICT (world_id) DO NOTHING;
