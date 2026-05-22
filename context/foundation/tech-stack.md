---
starter_id: fastapi
package_manager: uv
project_name: crochet-tracker
hints:
  language_family: python
  team_size: solo
  deployment_target: fly
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: first-class
  path_taken: custom
  quality_override: false
  self_check_answers:
    typed: true
    from_official_starter: true
    conventions: true
    docs_current: false
    can_judge_agent: true
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: false
---

## Why this stack

Solo data scientist building a personal crochet tracker in 4 weeks of after-hours work. FastAPI picked over the recommended Python web default (Django) because of existing fluency — the developer knows FastAPI well, has never used Django, and has no JS frontend experience. The stack runs FastAPI with Jinja2 templates + HTMX + Tailwind for server-rendered web pages: a Python-only pattern that respects the 4-week timeline and solo constraint. FastAPI clears all four agent-friendly gates (Pydantic-typed, conventional, popular within Python training data, well-documented), so the "strong typing" and "mainstream" soft preferences are satisfied natively without compensation. The trade-off: the PRD's offline-first NFR cannot be served by this stack and is being dropped — cross-device sync remains, but it requires connectivity during use rather than reconciling offline writes. Re-run /10x-prd to amend that NFR before bootstrapping. Fly is the default deployment target from the FastAPI card; GitHub Actions with auto-deploy on merge is the standard CI shape.
