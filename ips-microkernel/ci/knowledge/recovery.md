# CI Playbook: readiness and recovery corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-recovery -->

## Read when

Before remote push, read this leaf for health budgets, dependency liveness,
aggregate health convergence, retry churn, or recovery orchestration.

## Correction records

### Budget health checks for complete probes

- **Origin:** PR #8
  [run 29675397127](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29675397127)
- **Trigger:** A health check performs model, storage, broker, or other bounded
  probes.
- **Mistake:** The timeout did not cover the legitimate worst-case complete
  probe.
- **Correction:** Set the health timeout from the bounded sum of required probe
  budgets and cover the complete probe path.

### Poll direct liveness during recovery

- **Origin:** PR #8
  [run 29675923281](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29675923281)
- **Trigger:** A dependency can recover before aggregate container health
  converges.
- **Mistake:** Recovery waited on aggregate health and missed direct MinIO
  liveness recovery.
- **Correction:** After fault injection, poll the affected dependency's direct
  liveness signal with a bounded deadline.

### Quiesce retry churn before restoration

- **Origin:** PR #8
  [run 29676215101](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29676215101)
- **Trigger:** Broad faults plus automatic requeue obscure the recovery
  transition.
- **Mistake:** Requeue churn prevented a stable broker/result recovery check.
- **Correction:** Capture one semantic event, quiesce the actor, restore the
  dependency, restart only the target service when possible, and use bounded
  polling instead of unexplained fixed sleeps.

## Return

Return to publication Gate A after repairing the triggered readiness and
recovery scripts.
