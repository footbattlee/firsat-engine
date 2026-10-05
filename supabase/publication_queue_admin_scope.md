# Queue provenance from admin notifications

Apply publication_notification_snapshot.sql, then publication_queue_admin_scope.sql after the existing cloud_publication_queue.sql and publication_queue_scan_scope.sql schemas. This installs the admin dispatch trigger and checks notification provenance at slot creation, claim, and reservation.

Only a successful admin notification within the candidate's scan can enqueue it. Refreshing a price without another notification preserves an existing legitimate queue item and its original position. Both its originating scan and latest price scan must be complete before publication. Known published, publishing or failed Instagram outcomes cannot be retried automatically.

After reviewing and approving the affected rows, apply publication_queue_admin_cleanup.sql to hold old notifications incorrectly enqueued by price refreshes. It does not disable scheduling or change published/ambiguous held records.

## Isolated PostgreSQL tests

Install @electric-sql/pglite@0.3.14 in a disposable directory outside the repository. Set QUEUE_SQL_TEST_RUNTIME to that directory, then run:

```powershell
$env:QUEUE_SQL_TEST_RUNTIME = Join-Path $env:TEMP 'firsat-queue-sql-tests'
node --test tests/cloud_queue_sql.test.mjs
```

The tests execute the production functions against an isolated in-memory PostgreSQL database and never contact the production service.

Repeat notifications require at least a 15% drop from the last sent card price, even when the competitor gap also qualifies. The notification price is stored on successful admin dispatch. The queue stores its notification context separately so a later scan cannot erase the repeat basis. Legacy repeats without a reliable comparison price are held; a later new notification can restore them.
