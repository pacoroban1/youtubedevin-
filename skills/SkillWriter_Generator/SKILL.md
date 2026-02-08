---
name: SkillWriter_Generator
description: Generate production-grade SKILL.md files for this repo (single responsibility, evidence-first, with acceptance criteria + verifiers + fallbacks).
---

## When To Use
Use when you need to add a new skill (or improve an existing one) to fill a workflow gap without scope creep.

## Inputs
- `skill_name` (PascalCase or snake_case)
- `one_sentence_goal`
- `interfaces` (files, commands, API endpoints this skill touches)
- `success_signal` (what "Done" looks like)
- `known_failures` (top 3 ways it breaks)

## Preconditions
- You can point to at least one real interface in this repo (a file path, a Make target, a runner endpoint, or an n8n workflow file).
- If you cannot find a real interface, mark it **UNKNOWN** in the skill and add a discovery step.

## Steps
1. **Scope lock**: rewrite the goal to a single verb + object (example: "Generate narration WAV for VIDEO_ID").
1. **Evidence pass** (tool-first):
   - Find the relevant file(s): `rg -n "<keyword>"` and `ls` the parent folder.
   - Confirm endpoints/commands exist by reading code or running a non-destructive command (`make -n`, `curl -I`, etc).
1. **Write the SKILL.md** at `skills/<skill_name>/SKILL.md` with:
   - YAML frontmatter: `name`, `description`
   - Sections: `When To Use`, `Inputs`, `Preconditions`, `Steps`, `Acceptance Criteria`, `Verification`, `Failure Modes And Fallbacks`, `Notes`
1. **Acceptance criteria**: make them binary and observable (file exists, endpoint returns 200, artifact path exists, etc).
1. **Verification commands**: include copy/paste commands that actually run in this repo:
   - Prefer `make verify`, `make smoke`, `scripts/gate_local.sh`, `curl http://localhost:8000/...`
   - If a verifier is missing, add a discovery command (example: `make -qp | rg '^verify:'`).
1. **Fallbacks**: for each `known_failure`, write the safest fallback that keeps the pipeline moving (skip with artifact saved, retry bounded, or switch provider).
1. **Keep it modular**: if you find multiple responsibilities, split into multiple skills and link via `Notes`.

## Acceptance Criteria
- New skill is single-responsibility and maps to at least one real repo interface.
- Skill includes at least:
  - 2 acceptance criteria
  - 2 verification commands
  - 3 failure modes with explicit fallbacks

## Verification
- `test -f skills/SkillWriter_Generator/SKILL.md`
- `python3 -c 'from pathlib import Path; t=Path(\"skills/SkillWriter_Generator/SKILL.md\").read_text(\"utf-8\"); assert t.lstrip().startswith(\"---\\n\"); assert \"name:\" in t.split(\"---\",2)[1]; print(\"ok\")'`

## Failure Modes And Fallbacks
- Skill references non-existent endpoints: replace with **UNKNOWN** + add discovery steps.
- Skill has multiple responsibilities: split into multiple skills; keep the first as a thin orchestrator if needed.
- Skill's verifiers require secrets: add "offline mode" verifiers (format/JSON/schema checks) and note required env vars.

## Notes
- Never print secrets; use `.env.example` and "set in .env" wording.
- Prefer "save artifacts for manual review" over "hard fail" when running on autopilot.
