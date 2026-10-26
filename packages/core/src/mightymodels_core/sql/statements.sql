-- The statement catalogue. Statements scope root tables by repository_id and child tables by the
-- parent id the caller already holds. Every SELECT and RETURNING emits one json_object row.

-- name: ensure_repository
INSERT INTO repositories (repository_key) VALUES (:repository_key)
ON CONFLICT (repository_key) DO UPDATE SET repository_key = excluded.repository_key
RETURNING json_object('id', id, 'repository_key', repository_key);

-- name: repository_by_key
SELECT json_object('id', id, 'repository_key', repository_key)
FROM repositories
WHERE repository_key = :repository_key;

-- name: ticket_by_slug
SELECT projection FROM ticket_rows WHERE repository_id = :repository_id AND slug = :slug;

-- name: stage_ticket
INSERT INTO tickets (
  repository_id, slug, ticket, summary, branch, scope, plan_first, auto_escalate,
  issue, jira, models, context, validated_at
)
VALUES (
  :repository_id, :slug, :ticket, :summary, :branch, :scope, :plan_first, :auto_escalate,
  :issue, :jira, :models, :context, :validated_at
)
ON CONFLICT (repository_id, slug) DO UPDATE SET
  ticket = excluded.ticket,
  summary = excluded.summary,
  branch = excluded.branch,
  scope = excluded.scope,
  plan_first = excluded.plan_first,
  auto_escalate = excluded.auto_escalate,
  issue = excluded.issue,
  jira = excluded.jira,
  models = excluded.models,
  context = excluded.context,
  validated_at = excluded.validated_at
RETURNING json_object('id', id);

-- name: set_ticket_status
UPDATE tickets SET status = :status
WHERE repository_id = :repository_id AND slug = :slug;

-- name: unclosed_slugs_on_branch
SELECT json_object('slug', slug)
FROM tickets
WHERE repository_id = :repository_id AND branch = :branch AND status != 'closed'
ORDER BY slug;

-- name: unclosed_slug_pair_on_branch
SELECT json_object('slug', slug)
FROM tickets
WHERE repository_id = :repository_id AND branch = :branch AND status != 'closed'
LIMIT 2;

-- name: link_ticket_investigation
INSERT INTO ticket_investigations (ticket_id, investigation_id)
VALUES (:ticket_id, :investigation_id)
ON CONFLICT (ticket_id, investigation_id) DO NOTHING;

-- name: upsert_closing
INSERT INTO closings (ticket_id, closed_at, head, shipped, pr, gotchas, archive)
VALUES (:ticket_id, :closed_at, :head, :shipped, :pr, :gotchas, :archive)
ON CONFLICT (ticket_id) DO UPDATE SET
  closed_at = excluded.closed_at,
  head = excluded.head,
  shipped = excluded.shipped,
  pr = excluded.pr,
  gotchas = excluded.gotchas,
  archive = excluded.archive;

-- name: closing_of_ticket
SELECT json_object(
  'ticket_id', ticket_id,
  'closed_at', closed_at,
  'head', head,
  'shipped', shipped,
  'pr', pr,
  'gotchas', json(gotchas),
  'archive', archive
)
FROM closings
WHERE ticket_id = :ticket_id;

-- name: add_investigation
INSERT INTO investigations (repository_id, investigation_key, target, kind)
VALUES (:repository_id, :investigation_key, :target, :kind)
RETURNING json_object('id', id);

-- name: investigation_by_key
SELECT json_object(
  'id', id,
  'investigation_key', investigation_key,
  'target', target,
  'kind', kind,
  'created_at', created_at
)
FROM investigations
WHERE repository_id = :repository_id AND investigation_key = :investigation_key;

-- name: recorded_investigation_keys
SELECT json_object('investigation_key', investigation_key)
FROM investigations
WHERE repository_id = :repository_id
  AND investigation_key IN (SELECT value FROM json_each(:investigation_keys));

-- name: append_ledger_entry
INSERT INTO ledger_entries (investigation_id, seq, round, kind, text, source, cite, supersedes, at, head)
VALUES (:investigation_id, :seq, :round, :kind, :text, :source, :cite, :supersedes, :at, :head);

-- name: ledger_entries
SELECT json_object(
  'seq', seq,
  'round', round,
  'kind', kind,
  'text', text,
  'source', source,
  'cite', cite,
  'supersedes', json(supersedes),
  'at', at,
  'head', head
)
FROM ledger_entries
WHERE investigation_id = :investigation_id
ORDER BY seq
LIMIT :limit;

-- name: ledger_entry_count
SELECT json_object('count', count(*))
FROM ledger_entries
WHERE investigation_id = :investigation_id;

-- name: latest_rounds
SELECT json_object('investigation_key', i.investigation_key, 'round', max(l.round))
FROM investigations AS i
JOIN ledger_entries AS l ON l.investigation_id = i.id
WHERE i.repository_id = :repository_id
GROUP BY i.id
ORDER BY i.id DESC
LIMIT :limit;

-- name: task_by_key
SELECT json_object(
  'id', id,
  'task_key', task_key,
  'status', status,
  'owned', json(owned),
  'base', base,
  'commit', "commit",
  'reasons', json(reasons),
  'updated_at', updated_at
)
FROM tasks
WHERE ticket_id = :ticket_id AND task_key = :task_key;

-- name: tasks_of_ticket
SELECT json_object(
  'id', id,
  'task_key', task_key,
  'status', status,
  'owned', json(owned),
  'base', base,
  'commit', "commit",
  'reasons', json(reasons),
  'updated_at', updated_at
)
FROM tasks
WHERE ticket_id = :ticket_id
ORDER BY id
LIMIT :limit;

-- name: task_count
SELECT json_object('count', count(*))
FROM tasks
WHERE ticket_id = :ticket_id;

-- name: in_progress_tasks_started_by
SELECT json_object('task_key', t.task_key)
FROM tasks AS t
JOIN task_attempts AS a ON a.task_id = t.id
WHERE t.ticket_id = :ticket_id
  AND t.status = 'in-progress'
  AND a.worker = :worker
  AND a.id = (SELECT max(latest.id) FROM task_attempts AS latest WHERE latest.task_id = t.id)
ORDER BY t.task_key
LIMIT :limit;

-- name: upsert_task
INSERT INTO tasks (ticket_id, task_key, status, owned, base, "commit", reasons, updated_at)
VALUES (:ticket_id, :task_key, :status, :owned, :base, :commit, :reasons, :updated_at)
ON CONFLICT (ticket_id, task_key) DO UPDATE SET
  status = excluded.status,
  owned = excluded.owned,
  base = coalesce(tasks.base, excluded.base),
  "commit" = excluded."commit",
  reasons = excluded.reasons,
  updated_at = excluded.updated_at
RETURNING json_object('id', id);

-- name: record_task_verification
UPDATE tasks SET
  status = :status,
  "commit" = :commit,
  reasons = :reasons,
  updated_at = :updated_at
WHERE ticket_id = :ticket_id AND task_key = :task_key
RETURNING json_object('id', id);

-- name: add_task_attempt
INSERT INTO task_attempts (task_id, worker, mode, at)
VALUES (:task_id, :worker, :mode, :at);

-- name: attempts_by_worker
SELECT json_object('task_key', t.task_key, 'worker', a.worker, 'attempts', count(*))
FROM tasks AS t
JOIN task_attempts AS a ON a.task_id = t.id
WHERE t.ticket_id = :ticket_id
GROUP BY t.id, a.worker
ORDER BY min(a.id)
LIMIT :limit;

-- name: attempts_in_modes
SELECT json_object('count', count(*))
FROM task_attempts
WHERE task_id = :task_id AND mode IN (SELECT value FROM json_each(:modes));

-- name: add_task_failed_fix
INSERT INTO task_failed_fixes (task_id, hypothesis, at)
VALUES (:task_id, :hypothesis, :at);

-- name: task_failed_fixes
SELECT json_object('hypothesis', hypothesis)
FROM task_failed_fixes
WHERE task_id = :task_id
ORDER BY id
LIMIT :limit;

-- name: add_task_transition
INSERT INTO task_transitions (task_id, before, after, reasons, head, at)
VALUES (:task_id, :before, :after, :reasons, :head, :at);

-- name: latest_transitions_into
SELECT json_object(
  'task_key', t.task_key,
  'before', tr.before,
  'after', tr.after,
  'reasons', json(tr.reasons),
  'head', tr.head,
  'at', tr.at
)
FROM tasks AS t
JOIN task_transitions AS tr ON tr.task_id = t.id
WHERE t.ticket_id = :ticket_id
  AND tr.after IN (SELECT value FROM json_each(:statuses))
ORDER BY tr.id DESC
LIMIT :limit;

-- name: latest_transition_of_each_task_into
SELECT json_object(
  'task_key', t.task_key,
  'before', tr.before,
  'after', tr.after,
  'reasons', json(tr.reasons),
  'head', tr.head,
  'at', tr.at
)
FROM tasks AS t
JOIN task_transitions AS tr ON tr.task_id = t.id
WHERE t.ticket_id = :ticket_id
  AND tr.after IN (SELECT value FROM json_each(:statuses))
  AND tr.id = (
    SELECT max(latest.id)
    FROM task_transitions AS latest
    WHERE latest.task_id = t.id AND latest.after IN (SELECT value FROM json_each(:statuses))
  )
LIMIT :limit;

-- name: approve_contract_command
INSERT INTO contract_commands (
  ticket_id, command_key, task_key, argv, expect_exit, timeout, approved_by, approved_at, head
)
VALUES (
  :ticket_id, :command_key, :task_key, :argv, :expect_exit, :timeout, :approved_by, :approved_at,
  :head
);

-- name: contract_commands_of_ticket
SELECT json_object(
  'id', id,
  'command_key', command_key,
  'task_key', task_key,
  'argv', json(argv),
  'expect_exit', expect_exit,
  'timeout', timeout,
  'approved_by', approved_by,
  'approved_at', approved_at,
  'head', head
)
FROM contract_commands
WHERE ticket_id = :ticket_id
ORDER BY command_key
LIMIT :limit;

-- name: record_receipt
INSERT INTO receipts (
  contract_command_id, argv, outcome, exit, duration_ms, stdout_tail, stderr_tail, digest, head,
  phase, at
)
VALUES (
  :contract_command_id, :argv, :outcome, :exit, :duration_ms, :stdout_tail, :stderr_tail, :digest,
  :head, :phase, :at
);

-- name: latest_receipts
SELECT json_object(
  'command_key', c.command_key,
  'argv', json(r.argv),
  'outcome', r.outcome,
  'exit', r.exit,
  'duration_ms', r.duration_ms,
  'stdout_tail', r.stdout_tail,
  'stderr_tail', r.stderr_tail,
  'digest', r.digest,
  'head', r.head,
  'phase', r.phase,
  'at', r.at
)
FROM contract_commands AS c
JOIN receipts AS r ON r.contract_command_id = c.id
WHERE c.ticket_id = :ticket_id
  AND r.id = (SELECT max(latest.id) FROM receipts AS latest WHERE latest.contract_command_id = c.id)
LIMIT :limit;

-- name: journal_crashout
INSERT INTO crashouts (
  repository_id, at, ticket_key, branch, severity, verdict, rant, failures, root_cause,
  corrective_action, barked_back
)
VALUES (
  :repository_id, :at, :ticket_key, :branch, :severity, :verdict, :rant, :failures, :root_cause,
  :corrective_action, :barked_back
)
RETURNING json_object('id', id);

-- name: latest_crashouts
SELECT json_object(
  'id', id,
  'at', at,
  'ticket_key', ticket_key,
  'branch', branch,
  'severity', severity,
  'verdict', verdict,
  'rant', rant,
  'failures', json(failures),
  'root_cause', root_cause,
  'corrective_action', corrective_action,
  'barked_back', barked_back
)
FROM crashouts
WHERE repository_id = :repository_id
ORDER BY id DESC
LIMIT :limit;

-- name: crashout_count
SELECT json_object('count', count(*))
FROM crashouts
WHERE repository_id = :repository_id;

-- name: record_review_run
INSERT INTO review_runs (
  repository_id, run_key, ticket_key, scope, base, head, depth, emphasis, weights, personas,
  models, created_at
)
VALUES (
  :repository_id, :run_key, :ticket_key, :scope, :base, :head, :depth, :emphasis, :weights,
  :personas, :models, :created_at
)
RETURNING json_object('id', id);

-- name: record_review_models
UPDATE review_runs SET models = :models
WHERE repository_id = :repository_id AND run_key = :run_key;

-- name: review_run
SELECT json_object(
  'id', id,
  'run_key', run_key,
  'ticket_key', ticket_key,
  'scope', scope,
  'base', base,
  'head', head,
  'depth', depth,
  'emphasis', emphasis,
  'weights', json(weights),
  'personas', json(personas),
  'models', json(models),
  'created_at', created_at
)
FROM review_runs
WHERE repository_id = :repository_id AND run_key = :run_key;

-- name: latest_review_runs
SELECT json_object(
  'id', id,
  'run_key', run_key,
  'ticket_key', ticket_key,
  'scope', scope,
  'base', base,
  'head', head,
  'depth', depth,
  'emphasis', emphasis,
  'weights', json(weights),
  'personas', json(personas),
  'models', json(models),
  'created_at', created_at
)
FROM review_runs
WHERE repository_id = :repository_id
ORDER BY run_key DESC
LIMIT :limit;

-- name: latest_review_run_of_ticket
SELECT json_object(
  'id', id,
  'run_key', run_key,
  'ticket_key', ticket_key,
  'scope', scope,
  'base', base,
  'head', head,
  'depth', depth,
  'emphasis', emphasis,
  'weights', json(weights),
  'personas', json(personas),
  'models', json(models),
  'created_at', created_at
)
FROM review_runs
WHERE repository_id = :repository_id AND ticket_key = :ticket_key
ORDER BY run_key DESC
LIMIT 1;

-- name: upsert_review_finding
INSERT INTO review_findings (
  review_run_id, finding_key, sources, severity, kind, security, title, location, fix, verify,
  evidence_kind, evidence_cite, conflict
)
VALUES (
  :review_run_id, :finding_key, :sources, :severity, :kind, :security, :title, :location, :fix,
  :verify, :evidence_kind, :evidence_cite, :conflict
)
ON CONFLICT (review_run_id, finding_key) DO UPDATE SET
  sources = excluded.sources,
  severity = excluded.severity,
  kind = excluded.kind,
  security = excluded.security,
  title = excluded.title,
  location = excluded.location,
  fix = excluded.fix,
  verify = excluded.verify,
  evidence_kind = excluded.evidence_kind,
  evidence_cite = excluded.evidence_cite,
  conflict = excluded.conflict;

-- name: review_findings_of_run
SELECT json_object(
  'id', id,
  'finding_key', finding_key,
  'sources', json(sources),
  'severity', severity,
  'kind', kind,
  'security', security,
  'title', title,
  'location', location,
  'fix', fix,
  'verify', verify,
  'evidence_kind', evidence_kind,
  'evidence_cite', evidence_cite,
  'conflict', conflict
)
FROM review_findings
WHERE review_run_id = :review_run_id
ORDER BY length(finding_key), finding_key
LIMIT :limit;

-- name: upsert_review_disposition
INSERT INTO review_dispositions (review_finding_id, decision, reason, by, at)
VALUES (:review_finding_id, :decision, :reason, :by, :at)
ON CONFLICT (review_finding_id) DO UPDATE SET
  decision = excluded.decision,
  reason = excluded.reason,
  by = excluded.by,
  at = excluded.at;

-- name: review_dispositions_of_run
SELECT json_object(
  'id', d.id,
  'finding_key', f.finding_key,
  'decision', d.decision,
  'reason', d.reason,
  'by', d.by,
  'at', d.at
)
FROM review_findings AS f
JOIN review_dispositions AS d ON d.review_finding_id = f.id
WHERE f.review_run_id = :review_run_id
ORDER BY length(f.finding_key), f.finding_key
LIMIT :limit;

-- name: delete_review_dispositions
DELETE FROM review_dispositions
WHERE review_finding_id IN (
  SELECT f.id
  FROM review_findings AS f
  WHERE f.review_run_id = :review_run_id
    AND f.finding_key IN (SELECT value FROM json_each(:finding_keys))
);

-- name: upsert_review_outcome
INSERT INTO review_outcomes (review_disposition_id, result, "commit", reason, at)
VALUES (:review_disposition_id, :result, :commit, :reason, :at)
ON CONFLICT (review_disposition_id) DO UPDATE SET
  result = excluded.result,
  "commit" = excluded."commit",
  reason = excluded.reason,
  at = excluded.at;

-- name: review_outcomes_of_run
SELECT json_object(
  'finding_key', f.finding_key,
  'result', o.result,
  'commit', o."commit",
  'reason', o.reason,
  'at', o.at
)
FROM review_findings AS f
JOIN review_dispositions AS d ON d.review_finding_id = f.id
JOIN review_outcomes AS o ON o.review_disposition_id = d.id
WHERE f.review_run_id = :review_run_id
ORDER BY length(f.finding_key), f.finding_key
LIMIT :limit;

-- name: delete_review_outcomes
DELETE FROM review_outcomes
WHERE review_disposition_id IN (
  SELECT d.id
  FROM review_findings AS f
  JOIN review_dispositions AS d ON d.review_finding_id = f.id
  WHERE f.review_run_id = :review_run_id
    AND f.finding_key IN (SELECT value FROM json_each(:finding_keys))
);

-- name: upsert_similarity
INSERT INTO similarity (repository_id, kind, reference, text)
VALUES (:repository_id, :kind, :reference, :text)
ON CONFLICT (repository_id, kind, reference) DO UPDATE SET text = excluded.text;

-- name: similarity_of_reference
SELECT json_object('id', id, 'kind', kind, 'reference', reference, 'text', text, 'at', at)
FROM similarity
WHERE repository_id = :repository_id AND kind = :kind AND reference = :reference;

-- name: similarity_candidates
SELECT json_object('kind', s.kind, 'reference', s.reference, 'text', s.text)
FROM similarity_index
JOIN similarity AS s ON s.id = similarity_index.rowid
WHERE similarity_index MATCH :query
  AND s.repository_id = :repository_id
  AND (:kind IS NULL OR s.kind = :kind)
  AND (
    :excluded_reference IS NULL
    OR s.kind != :excluded_kind
    OR s.reference != :excluded_reference
  )
ORDER BY bm25(similarity_index)
LIMIT :limit;

-- name: add_scout_report
INSERT INTO scout_reports (repository_id, scout, target, report)
VALUES (:repository_id, :scout, :target, :report)
RETURNING json_object('id', id);

-- name: scout_report_of_target
SELECT json_object('id', id)
FROM scout_reports
WHERE repository_id = :repository_id AND scout = :scout AND target = :target
LIMIT 1;

-- name: upsert_session_pointer
INSERT INTO session_pointers (repository_id, session_id, kind, key, written_at)
VALUES (:repository_id, :session_id, :kind, :key, :written_at)
ON CONFLICT (repository_id, session_id) DO UPDATE
SET kind = excluded.kind, key = excluded.key, written_at = excluded.written_at;

-- name: session_pointer_of_session
SELECT json_object('kind', kind, 'key', key, 'written_at', written_at)
FROM session_pointers
WHERE repository_id = :repository_id AND session_id = :session_id
LIMIT 1;

-- name: prune_session_pointers
DELETE FROM session_pointers
WHERE repository_id = :repository_id AND written_at < :cutoff;
