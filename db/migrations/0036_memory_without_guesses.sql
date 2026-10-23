-- Best guess goes: a reviewer now chooses a held bill's treatment and approves
-- it (Choose and approve), so no booking is learnt as a guess any more. An
-- entry a guess left unconfirmed keeps its booking under review as a demoted
-- one does, until a person approves a bill booked that way.
UPDATE memory_entries SET status='demoted', updated_at=now() WHERE status='unconfirmed';
ALTER TABLE memory_entries DROP CONSTRAINT memory_entries_status_check;
ALTER TABLE memory_entries ADD CONSTRAINT memory_entries_status_check
    CHECK (status IN ('confirmed', 'demoted', 'retired', 'disabled'));
