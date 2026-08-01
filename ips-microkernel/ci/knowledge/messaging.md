# CI Playbook: messaging corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-messaging -->

## Read when

Before remote push, read this leaf for RabbitMQ or Celery queue topology,
confirms, acknowledgements, durability, or worker bootsteps.

## Correction records

### Make transient control queues exclusive

- **Origin:** PR #8
  [runs 29672715519 and 29673187660](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29673187660)
- **Trigger:** Celery control or event queues are transient under a broker that
  rejects unsafe non-exclusive topology.
- **Mistake:** RabbitMQ rejected transient non-exclusive queues.
- **Correction:** Keep business queues durable and make transient control or
  event queues exclusive instead of weakening broker policy or adding obsolete
  compatibility flags.

### Disable unused cluster bootsteps

- **Origin:** PR #8
  [run 29673641464](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/29673641464)
- **Trigger:** A single-purpose worker boots cluster coordination features it
  does not use.
- **Mistake:** Worker readiness failed after topology repair because gossip and
  mingle remained enabled unnecessarily.
- **Correction:** Disable unused gossip and mingle bootsteps and retain only the
  worker capabilities required by the accepted topology.

### Confirm publication before acknowledging source work

- **Origin:** Existing messaging reliability correction record
- **Trigger:** Processing publishes required downstream messages before source
  work is acknowledged.
- **Mistake:** Source acknowledgement could precede confirmation of required
  publications.
- **Correction:** Require publisher confirmation for every required message
  before acknowledging the source operation.

## Return

Return to publication Gate A after repairing only the triggered messaging
test/proof scripts.
