-- =============================================================================
-- ProjectPulse - sample analytical queries (PostgreSQL)
-- Handy for interviews / walkthroughs: each answers a real PMO question.
-- =============================================================================

-- 1. Which projects are over budget relative to the work they have delivered?
SELECT project_name, pct_complete, cpi, cost_variance
FROM vw_project_summary
WHERE cpi < 0.95
ORDER BY cpi;

-- 2. Velocity trend: last 3 sprints vs the 3 before, per project.
WITH ranked AS (
    SELECT project_id, completed_story_points AS velocity,
           ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY sprint_number DESC) AS rn
    FROM sprints
    WHERE status = 'Closed'
)
SELECT p.project_name,
       ROUND(AVG(velocity) FILTER (WHERE rn BETWEEN 1 AND 3), 0) AS recent_velocity,
       ROUND(AVG(velocity) FILTER (WHERE rn BETWEEN 4 AND 6), 0) AS prior_velocity,
       ROUND(100.0 * (AVG(velocity) FILTER (WHERE rn BETWEEN 1 AND 3)
                    / NULLIF(AVG(velocity) FILTER (WHERE rn BETWEEN 4 AND 6), 0) - 1), 1) AS change_pct
FROM ranked r
JOIN projects p USING (project_id)
GROUP BY p.project_name
ORDER BY change_pct;

-- 3. Average lead time and cycle time (days) by project.
SELECT p.project_name,
       ROUND(AVG(t.completion_date - t.created_date), 1) AS avg_lead_time_days,
       ROUND(AVG(t.completion_date - t.started_date), 1) AS avg_cycle_time_days
FROM tasks t
JOIN projects p USING (project_id)
WHERE t.status = 'Done'
GROUP BY p.project_name
ORDER BY avg_lead_time_days DESC;

-- 4. Who is overloaded? Planned sprint hours vs capacity over the last 8 weeks.
WITH recent AS (
    SELECT t.employee_id, SUM(t.planned_hours) AS hours
    FROM tasks t
    JOIN sprints s USING (sprint_id)
    WHERE s.end_date >= DATE '2026-09-30' - INTERVAL '8 weeks'
    GROUP BY t.employee_id
)
SELECT e.employee_name, e.department, r.hours,
       e.weekly_capacity_hours * 8 AS capacity,
       ROUND(r.hours / (e.weekly_capacity_hours * 8), 2) AS utilization
FROM recent r
JOIN employees e USING (employee_id)
ORDER BY utilization DESC
LIMIT 10;

-- 5. Retrospective effectiveness: action items vs attendance by project.
SELECT p.project_name,
       ROUND(AVG(c.attendance_rate) * 100, 1) AS attendance_pct,
       ROUND(AVG(c.action_items), 1)          AS avg_action_items
FROM scrum_ceremonies c
JOIN projects p USING (project_id)
WHERE c.ceremony_type = 'Retrospective'
GROUP BY p.project_name
ORDER BY attendance_pct;

-- 6. Risk ageing: open high-severity risks older than 60 days.
SELECT project_name, risk_description, risk_score, owner,
       DATE '2026-09-30' - identified_date AS age_days
FROM vw_open_risks
WHERE severity = 'High' AND DATE '2026-09-30' - identified_date > 60
ORDER BY age_days DESC;
