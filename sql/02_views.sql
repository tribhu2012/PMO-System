-- =============================================================================
-- ProjectPulse - analytical views (PostgreSQL)
-- Reusable building blocks for BI tools (Tableau / Power BI) and ad-hoc SQL.
-- The Streamlit app computes the same metrics in pandas (projectpulse/metrics.py)
-- so that they can respond to interactive date filters.
-- =============================================================================

-- Project-level EVM snapshot as of today's data (CPI, SPI, variances).
CREATE OR REPLACE VIEW vw_project_summary AS
WITH scope AS (
    SELECT project_id,
           SUM(story_points)                                         AS total_sp,
           SUM(story_points) FILTER (WHERE status = 'Done')          AS done_sp,
           COUNT(*) FILTER (WHERE status <> 'Done')                  AS tasks_remaining
    FROM tasks
    GROUP BY project_id
),
asof AS (
    SELECT MAX(GREATEST(created_date, COALESCE(completion_date, created_date))) AS as_of
    FROM tasks
),
risk AS (
    SELECT project_id,
           COUNT(*) FILTER (WHERE status IN ('Open','Mitigating'))                     AS open_risks,
           COUNT(*) FILTER (WHERE status IN ('Open','Mitigating') AND risk_score >= 15) AS high_risks,
           COALESCE(SUM(risk_score) FILTER (WHERE status IN ('Open','Mitigating')), 0)  AS risk_exposure
    FROM risks
    GROUP BY project_id
),
base AS (
    SELECT p.*,
           e.employee_name                                               AS project_manager,
           s.total_sp, s.done_sp, s.tasks_remaining,
           COALESCE(r.open_risks, 0)    AS open_risks,
           COALESCE(r.high_risks, 0)    AS high_risks,
           COALESCE(r.risk_exposure, 0) AS risk_exposure,
           s.done_sp::numeric / NULLIF(s.total_sp, 0)                    AS pct_complete,
           CASE WHEN p.actual_end_date IS NOT NULL THEN 1.0
                ELSE LEAST(1.0, GREATEST(0.0,
                     (a.as_of - p.start_date)::numeric
                     / NULLIF(p.planned_end_date - p.start_date, 0)))
           END                                                           AS pct_planned
    FROM projects p
    JOIN employees e ON e.employee_id = p.project_manager_id
    LEFT JOIN scope s ON s.project_id = p.project_id
    LEFT JOIN risk  r ON r.project_id = p.project_id
    CROSS JOIN asof a
)
SELECT project_id, project_name, project_manager, department, status, priority,
       start_date, planned_end_date, actual_end_date, budget, actual_cost,
       ROUND(pct_complete * 100, 1)                                  AS pct_complete,
       ROUND(budget * pct_planned, 2)                                AS planned_value,
       ROUND(budget * pct_complete, 2)                               AS earned_value,
       ROUND(budget * pct_complete - budget * pct_planned, 2)        AS schedule_variance,
       ROUND(budget * pct_complete - actual_cost, 2)                 AS cost_variance,
       ROUND((budget * pct_complete) / NULLIF(actual_cost, 0), 3)    AS cpi,
       ROUND(pct_complete / NULLIF(pct_planned, 0), 3)               AS spi,
       open_risks, high_risks, risk_exposure, tasks_remaining
FROM base;

-- Sprint velocity and commitment reliability.
CREATE OR REPLACE VIEW vw_sprint_metrics AS
SELECT s.sprint_id, s.project_id, p.project_name, s.sprint_number, s.start_date, s.end_date,
       s.status, s.planned_story_points, s.completed_story_points AS velocity,
       ROUND(s.completed_story_points::numeric / NULLIF(s.planned_story_points, 0), 3)
                                                              AS commitment_reliability,
       ROUND(AVG(s.completed_story_points) OVER (
             PARTITION BY s.project_id ORDER BY s.sprint_number
             ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1)    AS rolling_velocity_3
FROM sprints s
JOIN projects p ON p.project_id = s.project_id;

-- Employee delivery KPIs.
CREATE OR REPLACE VIEW vw_employee_performance AS
WITH t AS (
    SELECT employee_id,
           COUNT(*) FILTER (WHERE sprint_id IS NOT NULL)                         AS tasks_assigned,
           COUNT(*) FILTER (WHERE status = 'Done')                               AS tasks_done,
           COUNT(*) FILTER (WHERE status = 'Done' AND completion_date <= due_date) AS tasks_on_time,
           AVG(completion_date - started_date) FILTER (WHERE status = 'Done')    AS avg_cycle_days
    FROM tasks
    GROUP BY employee_id
),
pf AS (
    SELECT employee_id,
           SUM(story_points_completed) AS story_points_delivered,
           SUM(bugs_reopened)          AS bugs_reopened,
           SUM(stories_completed)      AS stories_completed,
           AVG(peer_review_score)      AS peer_review_score
    FROM performance
    GROUP BY employee_id
)
SELECT e.employee_id, e.employee_name, e.department, e.role,
       t.tasks_assigned, t.tasks_done,
       ROUND(t.tasks_done::numeric    / NULLIF(t.tasks_assigned, 0), 3) AS task_completion_rate,
       ROUND(t.tasks_on_time::numeric / NULLIF(t.tasks_done, 0), 3)     AS on_time_rate,
       pf.story_points_delivered,
       ROUND(pf.bugs_reopened::numeric / NULLIF(pf.stories_completed, 0), 3) AS defect_rate,
       ROUND(pf.peer_review_score, 2)                                    AS peer_review_score,
       ROUND(t.avg_cycle_days, 1)                                        AS avg_cycle_days
FROM employees e
JOIN t  ON t.employee_id  = e.employee_id
JOIN pf ON pf.employee_id = e.employee_id;

-- Open risk register with owner names.
CREATE OR REPLACE VIEW vw_open_risks AS
SELECT r.risk_id, p.project_name, r.category, r.risk_description, r.probability, r.impact,
       r.risk_score, e.employee_name AS owner, r.status, r.identified_date,
       r.mitigation_progress,
       CASE WHEN r.risk_score >= 15 THEN 'High'
            WHEN r.risk_score >= 8  THEN 'Medium'
            ELSE 'Low' END AS severity
FROM risks r
JOIN projects  p ON p.project_id  = r.project_id
JOIN employees e ON e.employee_id = r.owner_id
WHERE r.status IN ('Open','Mitigating');
