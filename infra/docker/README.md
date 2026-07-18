# Docker infrastructure

The root `compose.yaml` is the canonical integration definition.

When services are introduced:

- Keep one Dockerfile near each deployable area's source unless a documented
  build constraint requires another layout.
- Use the Compose project name `reactorfront-portfolio`.
- Let Compose generate scoped resource names; avoid `container_name`.
- Use project-owned networks and volumes by default.
- Add health checks that represent real readiness rather than process existence.
- Keep host paths, secrets, and local-machine assumptions out of committed
  configuration.

Global Docker cleanup commands are never part of this project's workflow.
