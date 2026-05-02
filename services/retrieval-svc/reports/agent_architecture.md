# Agent-First Engineering Framework

## Flow
User / Developer
→ Testing Agent
→ Bug Manager
→ Auto-Fix Agent
→ Self-Heal Loop
→ Council Governance Gate
→ Git Commit Agent
→ PR Agent

## Agent Roles
| Agent | Responsibility |
|---|---|
| Testing Agent | Runs pytest, smoke, OpenAPI checks |
| Bug Manager | Converts failed checks into bugs |
| Auto-Fix Agent | Applies safe fixes and reruns validation |
| Self-Heal Loop | Retries fixes and rolls back if needed |
| Agent Monitor | Checks Ollama/model/runtime health |
| Council Governance Gate | Blocks partial/failed council decisions |
| Git Commit Agent | Commits only after health + governance pass |
| PR Agent | Creates PR summary and PR command |

## Governance Rule
Commit is allowed only when:
- system health = PASS
- bugs = 0
- Ollama reachable
- required model available
- no partial council outcome
- no failed authors/reviewers
