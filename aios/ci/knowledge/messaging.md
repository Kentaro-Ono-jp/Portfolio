# Messaging knowledge

<!-- aios-role: knowledge -->
<!-- aios-rule: ci-knowledge-messaging -->

## Read when

Read this file for RabbitMQ or Celery queue topology, confirms,
acknowledgements, durability, or worker bootsteps.

## Durable rules

- Keep business queues durable.
- Make transient control or event queues exclusive rather than weakening
  broker policy.
- Disable cluster bootsteps a single-purpose worker does not use.
- Confirm required publications before acknowledging source work.
- Do not add compatibility flags merely to retain obsolete pinned-service
  behavior.

## Historical evidence

- PR #8
  [runs 29672715519](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29672715519)
  and
  [29673187660](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29673187660)
  showed RabbitMQ 4.3 rejecting transient non-exclusive Celery control and
  event queues. Fixes
  [`640ddbd`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/640ddbd9fc9dadc864cbc9d72c85ed8ff16135ab)
  and
  [`674fd1b`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/674fd1b5e96e0e700b2e06b284395671cecf28aa)
  made them exclusive.
- PR #8 [run 29673641464](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29673641464)
  then showed worker readiness failure without the queue rejection. Correction
  [`1826afd`](https://github.com/Kentaro-Ono-jp/Portfolio/commit/1826afd4cea1ac3eda2595e0db983f49cc9a37a4)
  removed unused gossip and mingle; the next
  [run 29674130187](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29674130187)
  passed. The causal link remains bounded historical inference.

Guards remain in
[`celery_app.py`](../../../apps/ml/src/reactorfront_ml/celery_app.py),
[`test_celery_app.py`](../../../apps/ml/tests/test_celery_app.py), the
[ML Dockerfile](../../../infra/docker/ml/Dockerfile), and
[`check_ml_compose_boundary.py`](../../../scripts/check_ml_compose_boundary.py).

## Return

Return to the calling CI procedure with only the applicable topology rule.
