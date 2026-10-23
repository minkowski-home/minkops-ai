# Active processing limits and updates

Every installed workflow uses the shared task/run and desktop-job contracts.
`MINKOPS_RUN_TIMEOUT_MINUTES` sets the cumulative active-processing budget on
both API and worker (integer 1–1440, default **45**). Set the same value on both
deployments. Cloud Run's worker task timeout must exceed that budget plus
cancellation/reconciliation time; the default deployment allows 60 minutes.

The task clock measures the union of executing hosted runs and native jobs,
so parallel bill children consume elapsed time once. Queueing, disconnected-PC
waiting before a claim, review, batch aggregation and explicit pauses do not
consume it. Resume continues the existing budget. Existing tasks begin their
measured budget at migration rather than being charged retroactively.

An independent worker monitor checks every ten seconds even while all hosted
lanes are occupied; API requests also enforce persisted deadlines. A busy
transaction can defer enforcement until the next check. Automatic Stop uses the
same dispatch and approval fences as operator Stop, records `time_limit`, and
requests hosted cancellation with the existing OpenAI credential. Cancellation
failures remain retryable; stop intent commits before provider I/O. This is not
a hard termination at an exact second during a network or database outage.

Completed proposals, outcomes, verified saves and recovery receipts remain
durable. A financial save already underway can finish and report its actual
outcome; new saves cannot start. A PC job whose task was stopped before it began
never starts. A stopped task cannot resume; start a new run, whose existing readback
and idempotency rules reconcile previous saves. Unfinished model reasoning is
not a resumable checkpoint. Future workflows must use these shared contracts
rather than adding their own timers or bypassing dispatch/approval fences.

The console compares its embedded build identifier with uncached `/version.json`
on launch and every 30 seconds. A new build shows **Refresh for latest version**;
refresh is explicit and uses the advertised build identifier in the navigation
URL to bypass cached HTML, including Electron's cache. It does not stop server
or companion work. This feature
first becomes available after the console containing it has been loaded.

Companion 0.8.1 reports downloading, ready, scheduled and failure states to the
same console. **Restart when safe** schedules installation only after the local
worker is idle and no receipt awaits acceptance. Existing automatic installation
on quit or while idle remains. A 0.8.0 companion can report readiness but cannot
accept the new restart command, so the console explains automatic installation.
The public installer, blockmap and `latest.yml` are verified and published
together through the existing release process. Unsigned distribution remains
the existing release limitation.
