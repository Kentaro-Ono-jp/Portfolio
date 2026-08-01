# CI Playbook: framework runtime corrections

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-framework-runtime -->

## Read when

Before remote push, read this leaf when the complete candidate changes
server-side state that must survive across independently bundled pages, routes,
handlers, workers, or entrypoints.

## Correction records

### Cross production bundle boundaries

- **Origin:** PR #57
  [run 30628514591](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30628514591)
- **Trigger:** One framework entrypoint writes server-side state and another
  independently bundled entrypoint consumes it.
- **Mistake:** A module-local test passed in one imported module instance while
  production split state across bundle or module instances.
- **Correction:** Exercise producer and consumer through separate production
  entrypoints and require bounded state continuity after module reload or
  equivalent independent loading.

## Return

Return to publication Gate A after repairing the triggered cross-entrypoint
test/proof scripts.
