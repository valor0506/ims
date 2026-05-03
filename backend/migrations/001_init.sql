-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create ENUM types
DO $$ BEGIN
    CREATE TYPE severity_enum AS ENUM ('P0', 'P1', 'P2', 'P3');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE status_enum AS ENUM ('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Work Items table (Source of Truth)
CREATE TABLE IF NOT EXISTS work_items (
    id VARCHAR(32) PRIMARY KEY,
    component_id VARCHAR(100) NOT NULL,
    severity severity_enum NOT NULL,
    status status_enum NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    rca JSONB,
    mttr_seconds INT GENERATED ALWAYS AS (
        CASE 
            WHEN resolved_at IS NOT NULL 
            THEN EXTRACT(EPOCH FROM (resolved_at - created_at))::INT
            ELSE NULL 
        END
    ) STORED
);

-- Constraint: Cannot close without RCA
ALTER TABLE work_items DROP CONSTRAINT IF EXISTS rca_required_for_close;
ALTER TABLE work_items ADD CONSTRAINT rca_required_for_close CHECK (
    status != 'CLOSED' OR (
        rca IS NOT NULL 
        AND rca->>'root_cause_category' IS NOT NULL
        AND rca->>'fix_applied' IS NOT NULL
        AND rca->>'prevention_steps' IS NOT NULL
    )
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_work_items_status ON work_items(status);
CREATE INDEX IF NOT EXISTS idx_work_items_active ON work_items(severity) WHERE status != 'CLOSED';
CREATE INDEX IF NOT EXISTS idx_work_items_component ON work_items(component_id);

-- TimescaleDB hypertable for aggregations
CREATE TABLE IF NOT EXISTS signal_aggregations (
    time TIMESTAMPTZ NOT NULL,
    component_id VARCHAR(100),
    severity severity_enum,
    count INT DEFAULT 1,
    avg_latency_ms FLOAT
);

-- Convert to hypertable (only if not already)
DO $$ BEGIN
    PERFORM create_hypertable('signal_aggregations', 'time', 
        chunk_time_interval => INTERVAL '1 hour',
        if_not_exists => TRUE
    );
EXCEPTION
    WHEN duplicate_table THEN null;
END $$;