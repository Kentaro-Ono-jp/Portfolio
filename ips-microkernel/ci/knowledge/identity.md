# Identity proof knowledge

<!-- ips-role: knowledge -->
<!-- ips-rule: ci-knowledge-identity -->

## Read when

Read this file after complete Proof implementation changes authenticated
identity, token claims, ownership expectations, or synthetic-provider fixtures.

## Entries

### Reject legacy ownership assumptions

- **Phase:** `pre-CI`
- **Trigger:** Runtime proof moves a resource from anonymous or legacy-system
  ownership to authenticated principal ownership.
- **Mistake:** Assertions or fixtures still expect the anonymous-era or legacy
  owner.
- **Check:** Do all affected setup, queries, and assertions use the stable
  authenticated principal and reject the obsolete owner assumption?
- **Guard:** Prove the authenticated and legacy principals are distinct and
  verify ownership through the production-shaped runtime path.
- **Evidence:** PR #57
  [run 30627309389](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30627309389).

### Derive exact validated token identity

- **Phase:** `pre-CI`
- **Trigger:** A synthetic identity provider or fixture supplies tokens used by
  runtime proof.
- **Mistake:** Proof treats a human-readable fixture or provider user ID as the
  OAuth `sub`, or guesses `iss`.
- **Check:** Are expected `iss` and `sub` derived from the validated real token
  used by the proof?
- **Guard:** Decode only through the production validation path and compare the
  resulting exact claims with persisted ownership and authorization evidence.
- **Evidence:** PR #57
  [run 30627826543](https://github.com/Kentaro-Ono-jp/Portfolio/actions/runs/30627826543).

## Return

Return to the calling CI procedure after applying only the triggered entries.
