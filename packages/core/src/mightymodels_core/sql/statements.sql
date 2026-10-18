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

-- name: ticket_by_id
SELECT json_object(
  'id', t.id,
  'slug', t.slug,
  'status', t.status,
  'ticket', t.ticket,
  'summary', t.summary,
  'branch', t.branch,
  'scope', t.scope,
  'plan_first', t.plan_first,
  'auto_escalate', t.auto_escalate,
  'issue', t.issue,
  'jira', t.jira,
  'models', json(t.models),
  'context', json(t.context),
  'validated_at', t.validated_at,
  'investigations', json((
    SELECT json_group_array(i.investigation_key ORDER BY ti.id)
    FROM ticket_investigations AS ti
    JOIN investigations AS i ON i.id = ti.investigation_id
    WHERE ti.ticket_id = t.id
  ))
)
FROM tickets AS t
WHERE t.id = :id;

-- name: ticket_by_slug
SELECT json_object(
  'id', t.id,
  'slug', t.slug,
  'status', t.status,
  'ticket', t.ticket,
  'summary', t.summary,
  'branch', t.branch,
  'scope', t.scope,
  'plan_first', t.plan_first,
  'auto_escalate', t.auto_escalate,
  'issue', t.issue,
  'jira', t.jira,
  'models', json(t.models),
  'context', json(t.context),
  'validated_at', t.validated_at,
  'investigations', json((
    SELECT json_group_array(i.investigation_key ORDER BY ti.id)
    FROM ticket_investigations AS ti
    JOIN investigations AS i ON i.id = ti.investigation_id
    WHERE ti.ticket_id = t.id
  ))
)
FROM tickets AS t
WHERE t.repository_id = :repository_id AND t.slug = :slug;

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
