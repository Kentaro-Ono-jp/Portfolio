# Implementation Prune Stage B checklist

<!-- ips-role: knowledge -->
<!-- ips-rule: stage-b-pre-review-checklist -->

## Read when

Read this checklist only after exact-head GitHub Actions succeeds or the exact
head fully satisfies an applicable governed qualified no-run exception, and
immediately before initial review or re-review dispatch. This execution point
is Implementation Prune Stage B inside publication Gate B. An absent workflow
under an exception is a limitation, never passing evidence.

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
  and skipped group and test-file N/NN inventory differs from the applicable
  exact-head evidence source.
- **Detect:** Read the live PR base and head full SHAs. For normal proof, read
  the successful exact-head Actions plan and inventory, including the exact
  source SHA and Actions run identity whenever any group is carried. For a qualified
  Markdown-only no-run head, require the complete exception contract, confirm
  that no exact-head Actions run exists, and use the exact committed-tree Gate
  A planner and required local proof as the inventory source. Parse both
  declared endpoints plus selected, executed, carried, and skipped groups and
  test-file N/NN counts from the live PR description and copyable review
  prompt. For that exception, also derive the complete live base-to-head path
  inventory and parse the description's declared exact Markdown path count and
  literal path list.
- **Pass:** Both declared base values equal the live base, both declared head
  values equal the live head, the PR evidence inventory and every N/NN count
  equal the applicable exact-head evidence source, every carried group is bound
  to a displayed successful source run whose SHA equals the stated baseline,
  and, when applicable, the
  declared Markdown count and literal path set exactly equal the complete live
  diff with every path ending in `.md`; any absent workflow is declared only
  as a qualified limitation, and the PR head is unchanged by metadata repair.
- **Repair:** Replace every declared endpoint with the live full SHA, publish
  the selected, executed, carried, and skipped inventory plus every group and
  test-file N/NN count from the applicable exact-head evidence source, and, for
  a Markdown-only exception, publish the exact changed-path count, every
  literal path, and the no-run limitation. Update the prompt, save the PR
  description, and read the live metadata back before dispatch.
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

### Validate JSON discriminator types before value equality

- **Trigger:** A Python JSON validator adds or changes an integer schema
  version or discriminator whose accepted value is checked by equality.
- **HEAD effect:** `moving`
- **Problem:** Python treats booleans as integers, so value equality accepts a
  JSON boolean as an integer discriminator and bypasses the malformed-contract
  guard.
- **Detect:** Parse one canonical valid document, then replace only the integer
  discriminator with each JSON boolean, canonicalize the mutation, and invoke
  the production parser while counting downstream repository or projection
  calls.
- **Pass:** The integer document succeeds; both boolean mutations fail with
  the canonical invalid-contract result before any downstream call.
- **Repair:** Require the exact parsed JSON integer type before comparing the
  supported value, and retain the canonical boolean mutation matrix at the
  production parser.
- **Origins:** PR #84
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/84#issuecomment-5205208334).

### Preserve composed governance invariants

- **Trigger:** A required-governance fragment mapping is added to or composed
  with the canonical required-text mapping, including when an existing path
  receives constraints from more than one source.
- **HEAD effect:** `moving`
- **Problem:** Normal dictionary overwrite semantics silently replace an
  earlier fragment tuple for the same path, while isolated helper tests pass
  without exercising the final production mapping.
- **Detect:** Import the production documentation checker, require every
  fragment from each composed source mapping to exist in the final canonical
  tuple for that path, then remove each source fragment once and validate the
  mutated file through the final integrated tuple.
- **Pass:** Every composed source fragment exists in the final canonical
  mapping, every pre-existing invariant for the same path remains present,
  and each one-fragment mutation fails production validation.
- **Repair:** Explicitly merge the added fragments with the completed
  canonical tuple for each repeated path and make mutation proof consume that
  final integrated tuple instead of a bespoke fragment mapping.
- **Origins:** PR #76
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/76#issuecomment-5167941319).

### Guard both boundaries of ordered workflow invariants

- **Trigger:** A required governance procedure adds or changes an action that
  must occur after one named predecessor and before one named successor.
- **HEAD effect:** `moving`
- **Problem:** A sequence guard checks only the successor boundary, so moving
  the action before its required predecessor still passes focused verification.
- **Detect:** Import the production governance checker, validate the canonical
  procedure, then mutate the procedure once by moving the action before its
  required predecessor and once by moving it after its required successor.
- **Pass:** The canonical procedure passes, and both one-boundary order
  mutations fail with the corresponding predecessor or successor diagnostic.
- **Repair:** Encode both ordering comparisons in the production checker and
  retain one focused negative test for each reversed boundary.
- **Origins:** PR #92
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/92#issuecomment-5219432881).

### Recompute evaluation aggregates from atomic outcomes

- **Trigger:** A governed evaluation report adds or changes sample outcomes,
  completeness, confusion, score-quality metrics, aggregate metrics, or gates.
- **HEAD effect:** `moving`
- **Problem:** A self-consistent aggregate, gate, and report-digest rewrite can
  pass even though the published values are not derived from evaluated sample
  outcomes.
- **Detect:** Generate one valid complete report, then keep its atomic outcomes
  unchanged while coherently changing an aggregate, every dependent gate, and
  the report digest; separately mutate each atomic identity or outcome field
  and recompute the report digest.
- **Pass:** The valid report passes; every aggregate-only coherent rewrite and
  every missing, duplicate, reordered, mislabeled, or altered atomic outcome
  fails before its supplied aggregates or gates are trusted.
- **Repair:** Preserve the minimal sanitized outcome for every declared sample
  and recompute completeness, confusion, score quality, class metrics, and
  gates exclusively from those outcomes before comparing supplied aggregates.
- **Origins:** PR #78
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/78#issuecomment-5169278027).

### Validate every policy-governed evaluation lineage field

- **Trigger:** An evaluation report carries a version or digest governed by
  the loaded evaluation policy, dataset snapshot, or expected artifact.
- **HEAD effect:** `moving`
- **Problem:** Schema shape and a self-recomputed report digest can certify a
  forged lineage value that the validator omitted from expected identity.
- **Detect:** Derive the complete expected lineage mapping from the loaded
  policy, snapshot, artifact, and declared model role; mutate each report
  lineage field once and recompute the report digest.
- **Pass:** The unmodified report passes, every governed lineage field is in
  the derived mapping, and every one-field coherent-digest mutation fails.
- **Repair:** Add every policy-, snapshot-, artifact-, role-, and model-governed
  field to expected identity and retain one coherent-digest mutation per field.
- **Origins:** PR #78
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/78#issuecomment-5169278027).

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

### Frame hashed structured identities unambiguously

- **Trigger:** An ETag, idempotency digest, or other strong identity hash adds
  or changes two or more accepted variable-length string fields.
- **HEAD effect:** `moving`
- **Problem:** Joining fields with a sentinel that is also accepted inside a
  field lets distinct structured identities produce the same hash input.
- **Detect:** Construct two otherwise-identical accepted identities by moving
  the chosen sentinel from the end of one adjacent field to the start of the
  next, then compare their final tokens; also replay one identity unchanged.
- **Pass:** The two distinct accepted structures produce different tokens,
  while the unchanged replay remains stable.
- **Repair:** Serialize an explicit typed structure with canonical key and
  value framing, or length-prefix every field, and retain the delimiter-
  relocation regression at the production identity function.
- **Origins:** PR #82
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/82#issuecomment-5194808938).

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

### Prove cross-boundary identities from producer-originated state

- **Trigger:** A consumer adds or changes an identity comparison with a record,
  manifest, or allowlist owned by another boundary.
- **HEAD effect:** `moving`
- **Problem:** A direct consumer-store seed uses an identity that the production
  producer cannot create, so verification passes while every real record fails
  the comparison.
- **Detect:** For every affected identity class, originate one accepted value
  through the production producer, capture the persisted consumer input, and
  compare it with the exact reviewed external record; mutate the producer value
  once and repeat the consumer decision.
- **Pass:** Producer-originated accepted state matches exactly one reviewed
  external identity and reaches the intended consumer outcome, while the
  mutated identity fails closed; no passing proof relies only on direct
  consumer-store seeding.
- **Repair:** Establish an explicit reviewed identity or binding representable
  by both boundaries, validate it before use, and replace the direct seed with
  producer-originated integration proof plus one mismatched negative.
- **Origins:** PR #84
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/84#issuecomment-5204630868).

### Normalize semantic timestamps before ordering

- **Trigger:** A request, response, or event sequence orders accepted RFC 3339
  timestamps and uses another field as a deterministic tie-break.
- **HEAD effect:** `moving`
- **Problem:** Raw timestamp text order differs from chronological order when
  valid offsets or variable fractional precision represent the instants.
- **Detect:** At the canonical schema, submit a real-time ascending sequence
  whose timestamp strings cross offsets and fractional widths, its real-time
  descending inverse, and two equivalent instants whose canonical tie-break
  fields are ascending then descending. Replay the ascending sequence and its
  inverse through every affected production boundary.
- **Pass:** The ascending sequence succeeds, the descending inverse fails, and
  equivalent instants are accepted only in deterministic canonical tie-break
  order without truncating accepted fractional precision.
- **Repair:** Parse the accepted timestamp into an offset-adjusted UTC whole
  second plus a precision-preserved fractional value, compare the normalized
  instant first, canonicalize the tie-break field, and retain positive plus
  inverse-negative fixtures at schema and production boundaries.
- **Origins:** PR #68
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/68#issuecomment-5152827215).

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

### Enforce rendered cloud policy quotas

- **Trigger:** Infrastructure code adds or changes a generated IAM managed,
  inline, or trust policy.
- **HEAD effect:** `moving`
- **Problem:** Syntax and mock plans pass while the rendered document exceeds
  the target cloud's creation quota.
- **Detect:** Render every generated policy from the canonical synthetic input,
  count characters using the provider's quota semantics, and compare each
  document with its exact managed, aggregate inline, or trust-policy limit and
  any declared future-change reserve.
- **Pass:** Every rendered policy is at or below its applicable creation quota,
  every declared reserve remains available, and the proof reports each exact
  size, reserve, and limit before any cloud API call.
- **Repair:** Separate stable maximum-authority guardrails from immutable exact
  identity enforcement, reduce duplicated statements without broadening the
  effective ceiling, add plan-time quota/reserve preconditions, and retain exact
  rendered-size assertions in AWS-free verification.
- **Origins:** PR #107
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/107#issuecomment-5230145388).

### Prove delegated identity ceilings adversarially

- **Trigger:** A permissions boundary or delegated-role policy adds or changes
  IAM policy mutation, role creation, role assumption, or pass-role authority.
- **HEAD effect:** `moving`
- **Problem:** The intended identity policy is narrow, but a replaceable or
  adversarial delegated identity policy can combine with the boundary to gain
  cross-environment, wrong-service, or otherwise broader authority.
- **Detect:** Combine the boundary with an adversarial wildcard identity grant
  for the affected action and enumerate every source role, every declared
  target, global and external targets, and synthesized undeclared ARNs that
  match each resource wildcard, across every environment and relevant service;
  also enumerate delegated policy-mutation actions on every mutable target.
- **Pass:** Every boundary PassRole resource is exact, only declared
  same-environment purpose and destination-service combinations are allowed,
  every undeclared wildcard-matching target is denied, and no delegated manager
  can replace, attach, delete, or update an owned role policy.
- **Repair:** Move policy ownership to the persistent bootstrap, remove
  delegated mutation grants, bind boundary resources to principal-derived
  environment and purpose, replace target wildcards with exact role ARNs, bind
  destination services, and retain the complete declared plus synthesized
  adversarial matrix.
- **Origins:** PR #107
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/107#issuecomment-5230145388).

### Bind destructive ID resources to ownership attributes

- **Trigger:** A destructive cloud action targets a resource whose generated
  identifier or ARN does not encode the accepted environment or owner name.
- **HEAD effect:** `moving`
- **Problem:** An account-level wildcard or ID wildcard lets unrelated
  resources satisfy the effective grant because no immutable enforcement layer
  binds every ownership attribute.
- **Detect:** For each affected resource type, evaluate one intended resource
  carrying every required ownership attribute and the same action against one
  unrelated or cross-environment resource with exactly one ownership attribute
  changed.
- **Pass:** Every correctly owned resource is allowed, while every unrelated,
  cross-environment, cross-repository, unmanaged, or persistent variant is
  denied by the effective intersection and its declared immutable ownership-
  enforcement layer. Each independently evaluated layer matches the published
  boundary architecture rather than being reported as narrower than it is.
- **Repair:** Require environment, repository, managed, and persistence tags in
  a bootstrap-owned policy that delegated roles cannot replace; when identity
  policy mutation is delegated, duplicate the ceiling in the boundary. Retain
  paired positives and one-attribute inverse negatives per ID resource type,
  plus proof that the selected enforcement policy is immutable.
- **Origins:** PR #107
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/107#issuecomment-5230145388).

### Model real cloud action resources and condition contexts

- **Trigger:** A generated IAM policy adds or changes a control-plane create,
  inventory, existing-resource mutation, or tagging action.
- **HEAD effect:** `moving`
- **Problem:** A synthetic positive supplies a resource ARN or condition key
  that the real cloud action does not expose, while the accepted create,
  inventory, mutation, or dependent tagging request is denied.
- **Detect:** From the target service's authorization reference, construct each
  required positive with its real create-time resource form and only the
  request, resource, or principal context keys available to that action;
  enumerate every rendered write action/resource form, execute each request
  independently against identity, boundary, and their effective intersection,
  then change only the ownership environment and repository.
- **Pass:** Every required real-context positive is allowed by identity,
  boundary, and their intersection; each ownership inverse is denied by the
  declared immutable enforcement layer and effective intersection; inventory
  succeeds without fabricated request tags; every required resource in a
  multi-resource authorization is exercised independently; and every dependent
  tagging action has its own passing case with an exact ownership-key ceiling.
  No rendered write verb or resource form is omitted from the inverse matrix.
- **Repair:** Split creation-time request-tag, unconditioned inventory, and
  existing-resource ownership-tag statements; use actual collection or
  resource-less create forms; grant the exact dependent tagging actions;
  require existing ownership for retagging where the service exposes resource
  tags; exercise every required parent/new resource separately; and retain the
  layer-by-layer positive, unowned, and inverse-negative matrix with explicit
  expectations for the enforcing layer and effective intersection.
- **Origins:** PR #107
  [re-review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/107#issuecomment-5230364500).

### Connect security allowlists to enforced trust claims

- **Trigger:** An automation trust contract adds or changes an allowed event,
  workflow, repository, environment, or other security-significant metadata
  field.
- **HEAD effect:** `moving`
- **Problem:** The allowlist is emitted only as output or documentation and
  does not participate in the actual trust decision.
- **Detect:** For every allowed metadata value, construct an otherwise exact
  token and require trust success; then replace only that value with one
  disallowed alternative while keeping every other claim exact.
- **Pass:** Every stated allowed value reaches exactly one enforceable trust
  condition and succeeds, while each single-field disallowed mutation fails.
- **Repair:** Encode the value into a provider-supported claim or customized
  subject, bind the trust policy to the exact result, and retain connected
  positive plus inverse-negative token cases.
- **Origins:** PR #107
  [initial review](https://github.com/Kentaro-Ono-jp/Portfolio/pull/107#issuecomment-5230145388).

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
