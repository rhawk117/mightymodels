-- The mightymodels schema. Drop and recreate: there are no migrations. open_database runs this
-- script inside BEGIN IMMEDIATE on a fresh file, so it holds no BEGIN or COMMIT.

CREATE TABLE repositories (
  id INTEGER CONSTRAINT pk_repositories PRIMARY KEY,
  repository_key TEXT NOT NULL,
  CONSTRAINT uq_repositories_key UNIQUE (repository_key)
) STRICT;

CREATE TABLE tickets (
  id INTEGER CONSTRAINT pk_tickets PRIMARY KEY,
  repository_id INTEGER NOT NULL,
  slug TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'staged',
  ticket TEXT NOT NULL,
  summary TEXT NOT NULL,
  branch TEXT NOT NULL,
  scope TEXT NOT NULL,
  plan_first INTEGER NOT NULL,
  issue INTEGER,
  jira TEXT,
  models TEXT NOT NULL,
  context TEXT NOT NULL,
  validated_at INTEGER NOT NULL DEFAULT (unixepoch()),
  auto_escalate INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT fk_tickets_repository FOREIGN KEY (repository_id)
    REFERENCES repositories (id) ON DELETE RESTRICT,
  CONSTRAINT uq_tickets_slug UNIQUE (repository_id, slug),
  CONSTRAINT uq_tickets_ticket UNIQUE (repository_id, ticket),
  CONSTRAINT ck_tickets_status CHECK (status IN ('staged', 'in-progress', 'closed')),
  CONSTRAINT ck_tickets_scope CHECK (scope IN ('sm', 'med', 'large')),
  CONSTRAINT ck_tickets_plan_first CHECK (plan_first IN (0, 1)),
  CONSTRAINT ck_tickets_auto_escalate CHECK (auto_escalate IN (0, 1)),
  CONSTRAINT ck_tickets_models CHECK (json_valid(models)),
  CONSTRAINT ck_tickets_context CHECK (json_valid(context))
) STRICT;
CREATE INDEX ix_tickets_branch ON tickets (repository_id, branch, status);

CREATE TABLE investigations (
  id INTEGER CONSTRAINT pk_investigations PRIMARY KEY,
  repository_id INTEGER NOT NULL,
  investigation_key TEXT NOT NULL,
  target TEXT NOT NULL,
  kind TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_investigations_repository FOREIGN KEY (repository_id)
    REFERENCES repositories (id) ON DELETE RESTRICT,
  CONSTRAINT uq_investigations_key UNIQUE (repository_id, investigation_key)
) STRICT;

CREATE TABLE ticket_investigations (
  id INTEGER CONSTRAINT pk_ticket_investigations PRIMARY KEY,
  ticket_id INTEGER NOT NULL,
  investigation_id INTEGER NOT NULL,
  CONSTRAINT fk_ticket_investigations_ticket FOREIGN KEY (ticket_id)
    REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT fk_ticket_investigations_investigation FOREIGN KEY (investigation_id)
    REFERENCES investigations (id) ON DELETE RESTRICT,
  CONSTRAINT uq_ticket_investigations_link UNIQUE (ticket_id, investigation_id)
) STRICT;
CREATE INDEX ix_ticket_investigations_investigation ON ticket_investigations (investigation_id);

CREATE TABLE ledger_entries (
  id INTEGER CONSTRAINT pk_ledger_entries PRIMARY KEY,
  investigation_id INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  round INTEGER NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  source TEXT NOT NULL,
  cite TEXT,
  supersedes TEXT NOT NULL DEFAULT '[]',
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  head TEXT,
  CONSTRAINT fk_ledger_entries_investigation FOREIGN KEY (investigation_id)
    REFERENCES investigations (id) ON DELETE CASCADE,
  CONSTRAINT uq_ledger_entries_seq UNIQUE (investigation_id, seq),
  CONSTRAINT ck_ledger_entries_kind
    CHECK (kind IN ('known', 'open', 'decision', 'resource', 'next')),
  CONSTRAINT ck_ledger_entries_source
    CHECK (source IN ('code-scout', 'web-scout', 'user', 'primary')),
  CONSTRAINT ck_ledger_entries_supersedes CHECK (json_valid(supersedes))
) STRICT;
CREATE INDEX ix_ledger_entries_round ON ledger_entries (investigation_id, round);

CREATE TABLE tasks (
  id INTEGER CONSTRAINT pk_tasks PRIMARY KEY,
  ticket_id INTEGER NOT NULL,
  task_key TEXT NOT NULL,
  status TEXT NOT NULL,
  owned TEXT NOT NULL,
  base TEXT,
  "commit" TEXT,
  reasons TEXT NOT NULL DEFAULT '[]',
  updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_tasks_ticket FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT uq_tasks_key UNIQUE (ticket_id, task_key),
  CONSTRAINT ck_tasks_status
    CHECK (status IN ('pending', 'in-progress', 'verified', 'failed', 'blocked', 'superseded')),
  CONSTRAINT ck_tasks_owned CHECK (json_valid(owned)),
  CONSTRAINT ck_tasks_reasons CHECK (json_valid(reasons))
) STRICT;

CREATE TABLE task_attempts (
  id INTEGER CONSTRAINT pk_task_attempts PRIMARY KEY,
  task_id INTEGER NOT NULL,
  worker TEXT NOT NULL,
  mode TEXT,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_task_attempts_task FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
  CONSTRAINT ck_task_attempts_worker CHECK (worker IN ('engineer', 'architect', 'intern')),
  CONSTRAINT ck_task_attempts_mode
    CHECK (mode IN ('recovery-implementation', 'systemic-refactor', 'diagnose-replan'))
) STRICT;
CREATE INDEX ix_task_attempts_task_mode ON task_attempts (task_id, mode);

CREATE TABLE task_failed_fixes (
  id INTEGER CONSTRAINT pk_task_failed_fixes PRIMARY KEY,
  task_id INTEGER NOT NULL,
  hypothesis TEXT NOT NULL,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_task_failed_fixes_task FOREIGN KEY (task_id)
    REFERENCES tasks (id) ON DELETE CASCADE
) STRICT;
CREATE INDEX ix_task_failed_fixes_task ON task_failed_fixes (task_id);

CREATE TABLE task_transitions (
  id INTEGER CONSTRAINT pk_task_transitions PRIMARY KEY,
  task_id INTEGER NOT NULL,
  before TEXT NOT NULL,
  after TEXT NOT NULL,
  reasons TEXT NOT NULL,
  head TEXT,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_task_transitions_task FOREIGN KEY (task_id)
    REFERENCES tasks (id) ON DELETE CASCADE,
  CONSTRAINT ck_task_transitions_before
    CHECK (before IN ('pending', 'in-progress', 'verified', 'failed', 'blocked', 'superseded')),
  CONSTRAINT ck_task_transitions_after
    CHECK (after IN ('pending', 'in-progress', 'verified', 'failed', 'blocked', 'superseded')),
  CONSTRAINT ck_task_transitions_reasons CHECK (json_valid(reasons))
) STRICT;
CREATE INDEX ix_task_transitions_after ON task_transitions (task_id, after);

CREATE TABLE contract_commands (
  id INTEGER CONSTRAINT pk_contract_commands PRIMARY KEY,
  ticket_id INTEGER NOT NULL,
  command_key TEXT NOT NULL,
  task_key TEXT,
  argv TEXT NOT NULL,
  expect_exit INTEGER NOT NULL DEFAULT 0,
  timeout INTEGER NOT NULL DEFAULT 300,
  approved_by TEXT NOT NULL,
  approved_at INTEGER NOT NULL DEFAULT (unixepoch()),
  head TEXT,
  CONSTRAINT fk_contract_commands_ticket FOREIGN KEY (ticket_id)
    REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT uq_contract_commands_key UNIQUE (ticket_id, command_key),
  CONSTRAINT ck_contract_commands_argv CHECK (json_valid(argv))
) STRICT;

CREATE TABLE receipts (
  id INTEGER CONSTRAINT pk_receipts PRIMARY KEY,
  contract_command_id INTEGER NOT NULL,
  argv TEXT NOT NULL,
  outcome TEXT NOT NULL,
  exit INTEGER,
  duration_ms INTEGER NOT NULL,
  stdout_tail TEXT NOT NULL,
  stderr_tail TEXT NOT NULL,
  digest TEXT NOT NULL,
  head TEXT,
  phase TEXT NOT NULL,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_receipts_contract_command FOREIGN KEY (contract_command_id)
    REFERENCES contract_commands (id) ON DELETE CASCADE,
  CONSTRAINT ck_receipts_argv CHECK (json_valid(argv)),
  CONSTRAINT ck_receipts_outcome
    CHECK (outcome IN ('pass', 'fail', 'timeout', 'not-found', 'refused', 'undecodable')),
  CONSTRAINT ck_receipts_phase CHECK (phase IN ('planning', 'task', 'review', 'landing'))
) STRICT;
CREATE INDEX ix_receipts_contract_command ON receipts (contract_command_id);

CREATE TABLE review_runs (
  id INTEGER CONSTRAINT pk_review_runs PRIMARY KEY,
  repository_id INTEGER NOT NULL,
  run_key TEXT NOT NULL,
  ticket_key TEXT,
  scope TEXT NOT NULL,
  base TEXT,
  head TEXT,
  depth TEXT NOT NULL,
  emphasis TEXT NOT NULL,
  weights TEXT NOT NULL,
  personas TEXT NOT NULL,
  models TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_review_runs_repository FOREIGN KEY (repository_id)
    REFERENCES repositories (id) ON DELETE RESTRICT,
  CONSTRAINT uq_review_runs_key UNIQUE (repository_id, run_key),
  CONSTRAINT ck_review_runs_scope CHECK (scope IN ('diff', 'branch', 'ticket', 'codebase')),
  CONSTRAINT ck_review_runs_depth CHECK (depth IN ('quick', 'standard', 'deep')),
  CONSTRAINT ck_review_runs_emphasis
    CHECK (emphasis IN ('release-readiness', 'maintainability', 'balanced', 'custom')),
  CONSTRAINT ck_review_runs_weights CHECK (json_valid(weights)),
  CONSTRAINT ck_review_runs_personas CHECK (json_valid(personas)),
  CONSTRAINT ck_review_runs_models CHECK (json_valid(models))
) STRICT;
CREATE INDEX ix_review_runs_ticket ON review_runs (repository_id, ticket_key, run_key);

CREATE TABLE review_findings (
  id INTEGER CONSTRAINT pk_review_findings PRIMARY KEY,
  review_run_id INTEGER NOT NULL,
  finding_key TEXT NOT NULL,
  sources TEXT NOT NULL,
  severity TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'defect',
  security INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL,
  location TEXT NOT NULL,
  fix TEXT NOT NULL,
  verify TEXT NOT NULL,
  evidence_kind TEXT,
  evidence_cite TEXT,
  conflict TEXT,
  CONSTRAINT fk_review_findings_run FOREIGN KEY (review_run_id)
    REFERENCES review_runs (id) ON DELETE CASCADE,
  CONSTRAINT uq_review_findings_key UNIQUE (review_run_id, finding_key),
  CONSTRAINT ck_review_findings_sources CHECK (json_valid(sources)),
  CONSTRAINT ck_review_findings_severity
    CHECK (severity IN ('Blocker', 'Critical', 'High', 'Medium', 'Low')),
  CONSTRAINT ck_review_findings_kind CHECK (kind IN ('defect', 'quality')),
  CONSTRAINT ck_review_findings_security CHECK (security IN (0, 1)),
  CONSTRAINT ck_review_findings_evidence_kind
    CHECK (evidence_kind IN ('metric', 'idiom', 'convention'))
) STRICT;
CREATE INDEX ix_review_findings_order
  ON review_findings (review_run_id, length(finding_key), finding_key);

CREATE TABLE review_dispositions (
  id INTEGER CONSTRAINT pk_review_dispositions PRIMARY KEY,
  review_finding_id INTEGER NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  by TEXT NOT NULL,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_review_dispositions_finding FOREIGN KEY (review_finding_id)
    REFERENCES review_findings (id) ON DELETE CASCADE,
  CONSTRAINT uq_review_dispositions_finding UNIQUE (review_finding_id),
  CONSTRAINT ck_review_dispositions_decision
    CHECK (decision IN ('fix', 'defer', 'accept-risk', 'dismiss'))
) STRICT;

CREATE TABLE review_outcomes (
  id INTEGER CONSTRAINT pk_review_outcomes PRIMARY KEY,
  review_disposition_id INTEGER NOT NULL,
  result TEXT NOT NULL,
  "commit" TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_review_outcomes_disposition FOREIGN KEY (review_disposition_id)
    REFERENCES review_dispositions (id) ON DELETE CASCADE,
  CONSTRAINT uq_review_outcomes_disposition UNIQUE (review_disposition_id),
  CONSTRAINT ck_review_outcomes_result CHECK (result IN ('fixed', 'failed', 'blocked'))
) STRICT;

CREATE TABLE crashouts (
  id INTEGER CONSTRAINT pk_crashouts PRIMARY KEY,
  repository_id INTEGER NOT NULL,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  ticket_key TEXT,
  branch TEXT,
  severity TEXT NOT NULL,
  verdict TEXT NOT NULL,
  rant TEXT NOT NULL,
  failures TEXT NOT NULL,
  root_cause TEXT NOT NULL,
  corrective_action TEXT NOT NULL,
  barked_back INTEGER NOT NULL,
  CONSTRAINT fk_crashouts_repository FOREIGN KEY (repository_id)
    REFERENCES repositories (id) ON DELETE RESTRICT,
  CONSTRAINT ck_crashouts_severity
    CHECK (severity IN ('mild-tilt', 'heated', 'crashout', 'full-meltdown')),
  CONSTRAINT ck_crashouts_verdict CHECK (verdict IN ('deserved', 'split', 'unreasonable')),
  CONSTRAINT ck_crashouts_failures CHECK (json_valid(failures)),
  CONSTRAINT ck_crashouts_barked_back CHECK (barked_back IN (0, 1))
) STRICT;
CREATE INDEX ix_crashouts_repository ON crashouts (repository_id);

CREATE TABLE similarity (
  id INTEGER CONSTRAINT pk_similarity PRIMARY KEY,
  repository_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  reference TEXT NOT NULL,
  text TEXT NOT NULL,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_similarity_repository FOREIGN KEY (repository_id)
    REFERENCES repositories (id) ON DELETE RESTRICT,
  CONSTRAINT uq_similarity_reference UNIQUE (repository_id, kind, reference),
  CONSTRAINT ck_similarity_kind
    CHECK (kind IN ('ledger-entry', 'scout-report', 'review-finding', 'crashout'))
) STRICT;

-- FTS5 holds no copy of the text: it reads similarity.text as its content, and the three triggers
-- carry every insert, update and delete of a similarity row into the index.
CREATE VIRTUAL TABLE similarity_index
  USING fts5(text, content='similarity', content_rowid='id', tokenize='unicode61');

CREATE TRIGGER similarity_index_insert AFTER INSERT ON similarity BEGIN
  INSERT INTO similarity_index (rowid, text) VALUES (new.id, new.text);
END;

CREATE TRIGGER similarity_index_delete AFTER DELETE ON similarity BEGIN
  INSERT INTO similarity_index (similarity_index, rowid, text) VALUES ('delete', old.id, old.text);
END;

CREATE TRIGGER similarity_index_update AFTER UPDATE ON similarity BEGIN
  INSERT INTO similarity_index (similarity_index, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO similarity_index (rowid, text) VALUES (new.id, new.text);
END;

CREATE TABLE scout_reports (
  id INTEGER CONSTRAINT pk_scout_reports PRIMARY KEY,
  repository_id INTEGER NOT NULL,
  scout TEXT NOT NULL,
  target TEXT NOT NULL,
  report TEXT NOT NULL,
  at INTEGER NOT NULL DEFAULT (unixepoch()),
  CONSTRAINT fk_scout_reports_repository FOREIGN KEY (repository_id)
    REFERENCES repositories (id) ON DELETE RESTRICT,
  CONSTRAINT ck_scout_reports_scout CHECK (scout IN ('code-scout', 'web-scout'))
) STRICT;
CREATE INDEX ix_scout_reports_target ON scout_reports (repository_id, scout, target);

CREATE TABLE closings (
  id INTEGER CONSTRAINT pk_closings PRIMARY KEY,
  ticket_id INTEGER NOT NULL,
  closed_at INTEGER NOT NULL DEFAULT (unixepoch()),
  head TEXT,
  shipped TEXT NOT NULL,
  pr TEXT,
  gotchas TEXT NOT NULL DEFAULT '[]',
  archive TEXT NOT NULL,
  CONSTRAINT fk_closings_ticket FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
  CONSTRAINT uq_closings_ticket UNIQUE (ticket_id),
  CONSTRAINT ck_closings_gotchas CHECK (json_valid(gotchas))
) STRICT;

PRAGMA user_version = 1;
