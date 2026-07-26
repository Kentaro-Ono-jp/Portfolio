# Readiness and recovery knowledge

<!-- aios-role: knowledge -->
<!-- aios-rule: ci-knowledge-recovery -->

## Read when

Read this file for health budgets, dependency liveness, aggregate health
convergence, retry churn, or recovery orchestration.

## Durable rules

- A health timeout must cover the legitimate worst-case complete probe.
- Recovery may precede aggregate container health. After fault injection, poll
  the affected dependency's direct liveness signal.
- Broad faults plus automatic requeue can obscure the transition under test.
  Capture one semantic event, quiesce the actor, restore the dependency, then
  restart only the target service when possible.
- Use bounded polling, not unexplained fixed sleeps.

## Historical evidence

- PR #8 [run 29675397127](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29675397127)
  showed the ML health timeout did not cover model, storage, and broker probes.
  Fix [`1f5c4b7`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/1f5c4b7db49dd3c4ed0e4f50bee60650cec4faea)
  advanced the chain.
- PR #8 [run 29675923281](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29675923281)
  showed MinIO liveness recovering before aggregate health. Fix
  [`d7e59e1`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/d7e59e115a361558198cf41bd624e3e50cf7c130)
  added direct liveness polling.
- PR #8 [run 29676215101](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29676215101)
  showed requeue churn during broker/result recovery. Fix
  [`3276457`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/3276457a7429bd885c626a6d41b2ac03a9a25a3c)
  captured one requeue and restarted only the worker. The chain closed at
  [run 29676610655](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29676610655).

Guards remain in the ML healthcheck in
[`compose.yaml`](../../../compose.yaml),
[`health.py`](../../../apps/ml/src/reactorfront_ml/health.py), and
[`verify_ml_runtime.py`](../../../scripts/verify_ml_runtime.py).

## Return

Return to the calling CI procedure after proving the exact liveness or recovery
transition.
