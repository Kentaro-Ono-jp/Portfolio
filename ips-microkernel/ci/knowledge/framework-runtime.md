# Framework runtime proof knowledge

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-framework-runtime -->

## Read when

Read this file after complete Proof implementation changes server-side state
that must survive across framework pages, routes, handlers, workers, or other
independently bundled entrypoints.

## Entries

### Prove state across production bundle boundaries

- **Phase:** `pre-CI`
- **Trigger:** Server-side state is written in one framework entrypoint and
  consumed by another entrypoint that production may bundle or load separately.
- **Mistake:** Module-local proof passes in one imported module instance while
  production splits the state across bundle or module instances.
- **Check:** Does proof cross the real write/read entrypoint boundary with
  production-shaped bundling or module reload behavior?
- **Guard:** Exercise the producer and consumer through separate framework
  entrypoints and require bounded state continuity after module reload or
  equivalent independent loading.
- **Evidence:** PR #57
  [run 30628514591](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30628514591).

## Return

Return to the calling CI procedure after proving the triggered cross-entrypoint
state boundary.
