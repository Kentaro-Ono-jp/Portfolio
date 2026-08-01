# Implementation Prune Stage B checklist

<!-- ips-role: knowledge -->
<!-- ips-rule: stage-b-pre-review-checklist -->

## Read when

Read this checklist only after exact-head GitHub Actions succeeds and
immediately before initial review or re-review dispatch. This execution point
is Implementation Prune Stage B inside publication Gate B.

Do not read it during first-pass implementation, publication Gate A,
pre-push hardening, CI Playbook selection, or Stage A recording.

## Rule contract

Each rule contains exactly Trigger, HEAD effect, Problem, Detect, Pass, Repair,
and Origins.

- `HEAD effect` is `neutral` when repairing the detected live problem does not
  change the Git commit, branch ref, tree, or PR head SHA; otherwise it is
  `moving`.
- `Detect` is a mechanically decidable procedure.
- `Pass` states the exact acceptable result.
- `Repair` gives the concrete correction procedure.
- `Origins` records provenance, not proof.

Rule titles are unique. Reuse or strengthen one canonical rule for a repeated
signal; never add a duplicate. Stage B rules have no Evidence, Proof, Status,
proved/unproved classification, or permanence claim.

## Rules

### Authenticate before request validation

- **Trigger:** A protected request boundary adds or changes path, header, body,
  or multipart validation.
- **HEAD effect:** `moving`
- **Problem:** Anonymous malformed input reaches validation before the
  capability-specific authentication boundary.
- **Detect:** Execute anonymous and authenticated malformed requests through
  every affected production request boundary and capture response class plus
  protected service-call count.
- **Pass:** Every anonymous case returns canonical authentication failure
  before validation with zero protected service calls; authenticated malformed
  cases reach canonical validation.
- **Repair:** Move the authentication dependency ahead of request validation
  on each affected route and add boundary tests for both actor states.
- **Origins:** PR #57
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/57#issuecomment-5142938286).

### Publish exact review endpoints

- **Trigger:** Initial review or re-review is ready to dispatch.
- **HEAD effect:** `neutral`
- **Problem:** The PR description or review prompt omits or misstates the live
  full base and head SHAs, or the description's selected, executed, carried,
  and skipped inventory differs from the exact-head Actions output.
- **Detect:** Read the live PR base and head full SHAs and the exact-head
  Actions plan, then parse both declared endpoints plus selected, executed,
  carried, and skipped groups from the live PR description and copyable review
  prompt.
- **Pass:** Both declared base values equal the live base, both declared head
  values equal the live head, the PR evidence inventory equals the exact-head
  Actions inventory, and the PR head is unchanged by metadata repair.
- **Repair:** Replace every declared endpoint with the live full SHA, publish
  the exact-head selected, executed, carried, and skipped inventory, update the
  prompt, save the PR description, and read the live metadata back before
  dispatch.
- **Origins:** PR #57
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/57#issuecomment-5143276537),
  PR #64
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/64#issuecomment-5150763750).

### Enforce exact operational record schemas

- **Trigger:** A Stage A, Stage B, or CI Playbook record contract or validator
  is added or changed.
- **HEAD effect:** `moving`
- **Problem:** Documentation verification filters for allowed labels and lets
  an unknown field heading or blank required value pass.
- **Detect:** For every affected record type, run a complete valid fixture,
  then mutate it once with an unknown field and once per blank required field.
- **Pass:** The valid fixture passes, duplicate policy remains intact, and
  every unknown-field or blank-value mutation fails.
- **Repair:** Parse every field heading instead of filtering allowed labels,
  require the exact ordered schema and non-empty values, and retain the full
  focused mutation matrix.
- **Origins:** PR #64
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/64#issuecomment-5150763750).

### Invalidate head-bound review evidence

- **Trigger:** A correction push moved the PR head before re-review.
- **HEAD effect:** `neutral`
- **Problem:** PR metadata presents old endpoints, CI, or a prior verdict as
  current-head evidence.
- **Detect:** Compare every current/preceding evidence label, workflow head,
  correction link, and review endpoint in the live PR description with the
  live PR head.
- **Pass:** Only successful evidence for the live head is current, all older
  evidence is preceding or superseded, every correction is linked, and the
  metadata read-back leaves the PR head unchanged.
- **Repair:** Relabel stale evidence, publish the live full base/head, attach
  the current exact-head workflow and correction chain, then read back the
  description before dispatch.
- **Origins:** PR #57
  [approved correction](https://github.com/Kentaro-Ono-jp/Portfolio/pull/57#issuecomment-5143423042).

### Authorize a target before idempotency classification

- **Trigger:** A protected resource mutation combines ownership hiding with an
  idempotency key or other target-bound replay record.
- **HEAD effect:** `moving`
- **Problem:** A reused key is classified before target authorization, so a
  hidden target returns a distinguishable conflict.
- **Detect:** Cross hidden and owned targets with reused and fresh keys through
  every affected adapter and inspect response plus mutation counts.
- **Pass:** Hidden targets always return the same not-found result with zero
  mutation, while owned-target replay and conflict behavior remains intact.
- **Repair:** Resolve target authorization before replay/conflict
  classification and add the complete hidden/owned by reused/fresh matrix to
  the affected adapter proof.
- **Origins:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788).

### Enforce closed request contracts at runtime

- **Trigger:** An OpenAPI request object uses `additionalProperties: false` or
  otherwise reserves server-derived fields.
- **HEAD effect:** `moving`
- **Problem:** The runtime model silently drops an extra property accepted by
  transport even though the published contract rejects it.
- **Detect:** Send a contract-valid authenticated request plus one
  reserved-looking extra property through the production request boundary and
  count protected service calls.
- **Pass:** Runtime returns canonical validation failure and makes zero
  protected service calls.
- **Repair:** Configure the runtime request model to forbid extras and add a
  real-boundary regression test using a valid body plus one extra property.
- **Origins:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788).

### Serialize only reachable discriminated states

- **Trigger:** A response union represents domain states whose discriminator
  constrains relationships among other fields.
- **HEAD effect:** `moving`
- **Problem:** Contract validation or runtime serialization accepts an
  impossible discriminator-and-field combination.
- **Detect:** Validate and serialize every reachable variant plus at least one
  impossible field combination per discriminator.
- **Pass:** Every reachable variant succeeds and every relationally impossible
  variant fails at both canonical schema and runtime serializer boundaries.
- **Repair:** Encode the relational invariant in the discriminated variants,
  regenerate types, and add positive and inverse-negative fixtures.
- **Origins:** PR #61
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5149897788).

### Enforce constrained request parameters at runtime

- **Trigger:** OpenAPI adds or changes a pattern, range, format, or enum for a
  path, query, header, or cookie parameter.
- **HEAD effect:** `moving`
- **Problem:** Runtime transport accepts malformed syntax and lets domain logic
  reclassify it as a different failure.
- **Detect:** Send an otherwise-valid authenticated request with one malformed
  constrained parameter and capture response plus service/state mutation.
- **Pass:** The production request boundary returns canonical validation
  failure before service invocation with zero state mutation.
- **Repair:** Apply the exact canonical constraint at the runtime parameter
  parser and add a production-boundary regression test.
- **Origins:** PR #61
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/61#issuecomment-5150104462).

### Exclude private browser content from failure artifacts

- **Trigger:** A browser or runtime verifier can retain submitted source,
  submitted private data, private profile claims, screenshots, video, trace
  resources, or HTML reports for failure diagnosis.
- **HEAD effect:** `moving`
- **Problem:** A credential-only pattern scan can approve a public failure
  artifact that still contains opaque private content or a rendered browser
  container.
- **Detect:** Register one opaque canary for each accepted private-content
  category and every profile identifier when first observed, before any
  assertion or reporter can serialize it. With encoders independent of the
  sanitizer, place raw, standard-base64, URL-safe padded and unpadded, strict
  percent, and lowercase-percent forms in both an ordinary file and ZIP
  member; place an unexpected observed profile value in failure JUnit; place
  trace and rendered-media containers under the public artifact root; then
  execute sanitization and the post-sanitization scan.
- **Pass:** Every statically or dynamically registered canary and every
  independently generated form is absent after sanitization, canary values are
  absent from the report, unexpected observed profile values cannot enter
  public failure text unregistered, browser trace/rendered containers are
  outside the public upload root, and any such container left in that root
  fails the upload gate.
- **Repair:** Move browser-owned binary and report containers to a non-uploaded
  root; register exact submitted canaries before browser navigation and every
  received reviewer/actor value before assertions; redact raw, standard-base64,
  URL-safe padded and unpadded, strict-percent, and lowercase-percent forms
  from public ordinary files and ZIP members; prove the matrix with independent
  encoders; re-scan with the same in-memory canaries; and block upload on any
  remaining private container or value.
- **Origins:** PR #68
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/68#issuecomment-5152433244).

## Execution and correction

A failed triggered rule blocks reviewer dispatch.

For a `moving` repair, correct the repository, append Stage A when applicable,
then return through publication Gate A: read selected CI Playbook leaves before
remote push, repair test/proof scripts, push one complete candidate, obtain new
exact-head CI, and run Stage B again. Do not duplicate the rule that found the
problem.

For a `neutral` repair, correct the live PR surface first and read it back. A
HEAD-neutral problem automatically meets the Stage B recording requirement.
After the repair, add or strengthen one deduplicated `neutral` rule with
mechanical Detect, exact Pass, and concrete Repair text. Then run Stage B again
without requiring a push or CI run solely to prove that rule. Successful
exact-head CI remains valid because the live product head did not move.

If repository persistence of a rule later moves `HEAD`, ordinary candidate CI
applies to the changed repository head; it does not certify the Stage B rule.

After an adjudicated review correction, update this checklist only after the
correction and only when it yields a cheap unambiguous machine check. If it
does not, write nothing. Never publish a `Stage B record: none` placeholder.

## Return

Return to publication after every triggered rule passes against the live
review candidate and metadata.
