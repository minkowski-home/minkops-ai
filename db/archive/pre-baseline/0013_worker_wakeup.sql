-- A singleton notification coalesces work across tenants; workflow rows still
-- own authorization and execution. Notifications commit with the originating run.
CREATE TABLE worker_wakeup (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    generation bigint NOT NULL DEFAULT 0,
    acknowledged bigint NOT NULL DEFAULT 0 CHECK (acknowledged <= generation),
    lease_until timestamptz,
    dispatch_token uuid
);
INSERT INTO worker_wakeup (singleton) VALUES (true);

CREATE FUNCTION notify_workflow_worker() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' OR NEW.state IS DISTINCT FROM OLD.state THEN
        UPDATE worker_wakeup SET generation=generation+1 WHERE singleton;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER workflow_worker_wakeup AFTER INSERT OR UPDATE OF state ON workflow_runs
FOR EACH ROW EXECUTE FUNCTION notify_workflow_worker();
