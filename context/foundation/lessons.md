# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Destructive initial-migration downgrade should be flagged in the migration file itself

**Context:** alembic/versions/<hash>_initial_schema.py (revision 1, down_revision=None)

**Problem:** downgrade() drops all tables and enum types with no in-file warning. The risk is documented in plan.md's Migration Notes, but a future reader of the migration file alone (without the plan) wouldn't know downgrade is fully destructive.

**Rule:** Add a comment in downgrade() of any migration that drops tables/data, noting it's destructive and under what conditions it's safe to run.

**Applies to:** All Alembic migrations, especially the initial schema migration and any migration with a destructive downgrade.
