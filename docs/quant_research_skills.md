# Quant Research Skills

Quant Research Skills are research protocols, not loose prompts.

Each skill should define:

- required input fields
- minimum data level
- baseline requirements
- failure conditions
- evaluation profile
- output schema

Skills keep Harness from free-associating. They tell the system how a strategy family should be
tested before it is allowed to produce more variants or spend optimizer budget.

Initial skill directory:

```text
skills/
├── event_driven_evaluation/SKILL.md
├── failed_breakout_punishment/SKILL.md
└── funding_crowding_fade/SKILL.md
```

These files are deliberately human-readable first. A later registry can parse frontmatter and route
ResearchTasks to skill-specific evaluators.
