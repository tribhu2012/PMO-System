-- =============================================================================
-- ProjectPulse - PostgreSQL schema
-- Project Portfolio Management & Agile Analytics Platform (TechNova Solutions)
--
-- Run:  psql "$DATABASE_URL" -f sql/01_schema.sql
-- The loader (scripts/load_data.py) executes this file automatically.
--
-- Columns tagged "ext" extend the original brief so the data behaves like a
-- real Jira export (sprint membership, issue type, work start date, risk
-- lifecycle). They are what make cycle time, burndowns and risk trends possible.
-- =============================================================================

DROP VIEW  IF EXISTS vw_project_summary, vw_sprint_metrics, vw_employee_performance,
                     vw_open_risks CASCADE;
DROP TABLE IF EXISTS performance, scrum_ceremonies, risks, tasks, sprints,
                     projects, employees, project_history CASCADE;

-- -----------------------------------------------------------------------------
-- employees
-- -----------------------------------------------------------------------------
CREATE TABLE employees (
    employee_id            INTEGER      PRIMARY KEY,
    employee_name          VARCHAR(100) NOT NULL,
    department             VARCHAR(50)  NOT NULL,
    role                   VARCHAR(60)  NOT NULL,
    hire_date              DATE         NOT NULL,
    weekly_capacity_hours  INTEGER      NOT NULL,
    CONSTRAINT ck_emp_capacity CHECK (weekly_capacity_hours BETWEEN 1 AND 60)
);
CREATE INDEX ix_employees_department ON employees (department);

-- -----------------------------------------------------------------------------
-- projects
-- -----------------------------------------------------------------------------
CREATE TABLE projects (
    project_id          INTEGER       PRIMARY KEY,
    project_name        VARCHAR(100)  NOT NULL UNIQUE,
    description         VARCHAR(200),                                   -- ext
    project_manager_id  INTEGER       NOT NULL REFERENCES employees (employee_id),
    department          VARCHAR(50)   NOT NULL,
    start_date          DATE          NOT NULL,
    planned_end_date    DATE          NOT NULL,
    actual_end_date     DATE,
    budget              NUMERIC(14,2) NOT NULL,
    actual_cost         NUMERIC(14,2) NOT NULL,
    status              VARCHAR(20)   NOT NULL,
    priority            VARCHAR(10)   NOT NULL,
    CONSTRAINT ck_proj_dates    CHECK (planned_end_date > start_date),
    CONSTRAINT ck_proj_budget   CHECK (budget > 0),
    CONSTRAINT ck_proj_status   CHECK (status IN ('On Track','At Risk','Delayed','Completed','On Hold')),
    CONSTRAINT ck_proj_priority CHECK (priority IN ('Critical','High','Medium','Low'))
);
CREATE INDEX ix_projects_department ON projects (department);

-- -----------------------------------------------------------------------------
-- sprints
-- -----------------------------------------------------------------------------
CREATE TABLE sprints (
    sprint_id               INTEGER     PRIMARY KEY,
    project_id              INTEGER     NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    sprint_number           INTEGER     NOT NULL,
    sprint_name             VARCHAR(60),                                -- ext
    start_date              DATE        NOT NULL,
    end_date                DATE        NOT NULL,
    status                  VARCHAR(10) NOT NULL,                       -- ext: Closed / Active
    planned_story_points    INTEGER     NOT NULL,
    completed_story_points  INTEGER     NOT NULL,
    CONSTRAINT ck_sprint_dates CHECK (end_date > start_date),
    CONSTRAINT ck_sprint_sp    CHECK (completed_story_points >= 0),
    CONSTRAINT uq_sprint_number UNIQUE (project_id, sprint_number)
);
CREATE INDEX ix_sprints_project_id ON sprints (project_id);

-- -----------------------------------------------------------------------------
-- tasks
-- -----------------------------------------------------------------------------
CREATE TABLE tasks (
    task_id          INTEGER      PRIMARY KEY,
    task_key         VARCHAR(20)  NOT NULL UNIQUE,                      -- ext (e.g. PHX-142)
    project_id       INTEGER      NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    sprint_id        INTEGER      REFERENCES sprints (sprint_id) ON DELETE SET NULL,  -- ext
    employee_id      INTEGER      REFERENCES employees (employee_id),
    task_name        VARCHAR(200) NOT NULL,
    issue_type       VARCHAR(10)  NOT NULL,                             -- ext: Story/Task/Bug/Spike
    story_points     INTEGER      NOT NULL,
    planned_hours    NUMERIC(7,1) NOT NULL,
    actual_hours     NUMERIC(7,1),
    status           VARCHAR(15)  NOT NULL,
    priority         VARCHAR(10)  NOT NULL,
    created_date     DATE         NOT NULL,
    started_date     DATE,                                              -- ext (cycle time)
    due_date         DATE         NOT NULL,
    completion_date  DATE,
    CONSTRAINT ck_task_sp         CHECK (story_points IN (1,2,3,5,8,13)),
    CONSTRAINT ck_task_status     CHECK (status IN ('To Do','In Progress','In Review','Blocked','Done')),
    CONSTRAINT ck_task_completion CHECK (completion_date IS NULL OR completion_date >= created_date)
);
CREATE INDEX ix_tasks_project_id  ON tasks (project_id);
CREATE INDEX ix_tasks_sprint_id   ON tasks (sprint_id);
CREATE INDEX ix_tasks_employee_id ON tasks (employee_id);
CREATE INDEX ix_tasks_status      ON tasks (status);

-- -----------------------------------------------------------------------------
-- risks
-- -----------------------------------------------------------------------------
CREATE TABLE risks (
    risk_id              INTEGER     PRIMARY KEY,
    project_id           INTEGER     NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    category             VARCHAR(20) NOT NULL,                          -- ext
    risk_description     TEXT        NOT NULL,
    probability          INTEGER     NOT NULL,
    impact               INTEGER     NOT NULL,
    risk_score           INTEGER     NOT NULL,
    owner_id             INTEGER     NOT NULL REFERENCES employees (employee_id),
    status               VARCHAR(12) NOT NULL,
    identified_date      DATE        NOT NULL,                          -- ext
    resolved_date        DATE,                                          -- ext
    mitigation_progress  INTEGER     NOT NULL,                          -- ext (0-100 %)
    CONSTRAINT ck_risk_prob       CHECK (probability BETWEEN 1 AND 5),
    CONSTRAINT ck_risk_impact     CHECK (impact BETWEEN 1 AND 5),
    CONSTRAINT ck_risk_score      CHECK (risk_score = probability * impact),
    CONSTRAINT ck_risk_status     CHECK (status IN ('Open','Mitigating','Closed','Accepted')),
    CONSTRAINT ck_risk_mitigation CHECK (mitigation_progress BETWEEN 0 AND 100)
);
CREATE INDEX ix_risks_project_id ON risks (project_id);

-- -----------------------------------------------------------------------------
-- scrum_ceremonies
-- -----------------------------------------------------------------------------
CREATE TABLE scrum_ceremonies (
    ceremony_id       INTEGER      PRIMARY KEY,
    project_id        INTEGER      NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    sprint_id         INTEGER      REFERENCES sprints (sprint_id) ON DELETE SET NULL,  -- ext
    ceremony_type     VARCHAR(20)  NOT NULL,
    ceremony_date     DATE         NOT NULL,
    attendance_rate   NUMERIC(4,3) NOT NULL,
    duration_minutes  INTEGER      NOT NULL,
    action_items      INTEGER      NOT NULL,
    CONSTRAINT ck_cer_type       CHECK (ceremony_type IN ('Sprint Planning','Daily Standup','Sprint Review','Retrospective')),
    CONSTRAINT ck_cer_attendance CHECK (attendance_rate BETWEEN 0 AND 1)
);
CREATE INDEX ix_scrum_ceremonies_project_id ON scrum_ceremonies (project_id);

-- -----------------------------------------------------------------------------
-- performance  (one row per employee per sprint they worked in)
-- -----------------------------------------------------------------------------
CREATE TABLE performance (
    employee_id             INTEGER      NOT NULL REFERENCES employees (employee_id),
    sprint_id               INTEGER      NOT NULL REFERENCES sprints (sprint_id) ON DELETE CASCADE,
    stories_assigned        INTEGER      NOT NULL,
    stories_completed       INTEGER      NOT NULL,
    story_points_completed  INTEGER      NOT NULL,
    bugs_reopened           INTEGER      NOT NULL,
    peer_review_score       NUMERIC(3,1) NOT NULL,
    PRIMARY KEY (employee_id, sprint_id),
    CONSTRAINT ck_perf_stories CHECK (stories_completed <= stories_assigned),
    CONSTRAINT ck_perf_peer    CHECK (peer_review_score BETWEEN 1 AND 5)
);

-- -----------------------------------------------------------------------------
-- project_history (ext) - archived PMO close-out snapshots, 2019-2024.
-- Training data for the delay-prediction model.
-- -----------------------------------------------------------------------------
CREATE TABLE project_history (
    history_id                INTEGER          PRIMARY KEY,
    project_code              VARCHAR(20)      NOT NULL,
    department                VARCHAR(50)      NOT NULL,
    close_year                INTEGER          NOT NULL,
    budget_utilization        DOUBLE PRECISION NOT NULL,  -- AC / EV at mid-project
    open_risks                INTEGER          NOT NULL,
    avg_resource_utilization  DOUBLE PRECISION NOT NULL,
    sprint_velocity           DOUBLE PRECISION NOT NULL,  -- avg completed SP, last 3 sprints
    tasks_remaining           INTEGER          NOT NULL,
    delayed                   INTEGER          NOT NULL   -- 1 = finished after planned end
);
