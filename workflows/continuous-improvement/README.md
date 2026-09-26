# Continuous Improvement Workflow

Owner: **Horizon, President Advisor**

## Inputs
- verified project outcomes and QA reports
- capability registry
- approved web/repository research
- dependency/model/provider release notes
- incident and failure reports
- user/President feedback

## Outputs
- evidence-backed observation
- capability gap or opportunity
- experiment proposal
- sandbox result
- adoption/rejection recommendation
- candidate memory/skill update

## State machine
`observed -> verified -> proposed -> approved_for_test -> sandboxed -> evaluated -> approved_for_promotion -> implemented -> monitored`

Rejected or superseded proposals remain auditable.

## Improvement record template
```yaml
id: IMP-YYYY-NNN
status: observed
claim: ""
evidence: []
counter_evidence: []
confidence: low|medium|high
affected_capabilities: []
expected_value: ""
cost: ""
risk: ""
experiment:
  hypothesis: ""
  steps: []
  success_metrics: []
  rollback: ""
approvals: []
outcome: ""
lessons: []
```

## Guardrail
Horizon may continuously think and propose, but continuous self-improvement means continuous **evaluation and learning**, not uncontrolled self-modification. Production changes pass review and approval gates.
