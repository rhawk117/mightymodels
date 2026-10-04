---
type: llm
focus: { source: file, path: fixtures/new/tf-guard/plugin-plan.json }
---

The file is a plugin plan record for a Terraform plugin named tf-guard. The person accepted every proposed mechanism switch upfront.

PASS if all of these hold:
- A hook that denies terraform apply and destroy is not a plugin component; the need is recorded under outside_plugin as a permission rule in the project settings, with advice and the decision recorded.
- The validate_module idea is recorded as a skill whose allowed-tools pre-approve terraform validate, with the advice and the decision recorded.
- A hook that runs terraform fmt after edits is kept, and a skill that reviews plans for replacements is kept.

FAIL if the denial hook or an MCP server is still a planned component, or if a switch is made without the advice and decision recorded.
