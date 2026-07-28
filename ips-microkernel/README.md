# iPS Microkernel

<!-- ips-context: human-only -->

> Human-facing architecture narrative. This file has no runtime role and is
> deliberately excluded from the routed governance graph.

This page explains the architecture; it does not participate in its runtime.
AI agents operating through the iPS Microkernel must start at
`GIT_AGENTS.md`, follow the thin work router, and load only the route selected
for the current state. They must not preload this origin story. Mechanical
documentation verification may inspect the file, but the narrative is not part
of the agent's working context.

The public product in this repository remains the
[Document Intelligence and Human Review Platform](../README.md). The iPS
Microkernel is the document-driven governance architecture used to design,
implement, review, verify, and evolve that product. Keeping these identities
separate lets the product README remain product-first while this page preserves
the architectural idea and its origin.

## The name

**iPS Microkernel** expands to:

> **intentional Progressive-disclosure System Microkernel**

The lowercase `i`, uppercase `P`, and uppercase `S` are deliberate. The name
echoes the familiar styling of iPS cells and the product-conscious naming story
behind that styling. It is also a technical acronym in which every word states
an architectural constraint.

### intentional

Not reading is a design decision.

Failure to load an unrelated document is not missing context, incomplete
initialization, or an agent mistake. Information that the current task does not
need is intentionally left unloaded. The system treats tokens, attention, and
decision surface as finite runtime resources.

This changes the governing question from:

> What might be useful enough to preload?

to:

> What does the current state prove is necessary now?

### Progressive-disclosure

The complete operating knowledge is not disclosed at startup. The system
reveals only the router, procedure, reference, knowledge, or exception selected
by the current state.

A normal task begins with a thin router. A concrete signal then discloses one
next capability:

- an unfocused change discloses the focus procedure;
- an accepted issue and branch disclose the implementation procedure;
- a complete staged candidate discloses the CI router;
- a contested permission boundary discloses the authority reference;
- a dependency failure discloses dependency knowledge;
- a qualified Markdown-only change discloses its exception.

Unselected siblings remain dormant. Disclosure advances one explicit
transition at a time and returns to the caller when the selected operation has
changed the state.

### System

This is not merely a tidy collection of Markdown files.

The documents form a governance system with:

- explicit runtime roles;
- state-based routes and transitions;
- canonical ownership of rules;
- authority and safety boundaries;
- procedures with defined inputs and returns;
- evidence requirements;
- exception qualification;
- dependency and reachability constraints;
- executable inspection of the complete topology.

The prose communicates the contract. Paths, markers, links, inventories, and
tests make important parts of that contract machine-visible.

### Microkernel

Startup retains only the smallest dispatch layer. Large knowledge bodies,
special cases, and detailed procedures live outside that kernel and are loaded
only when selected.

The architecture replaces a monolithic, always-on prompt with a thin routing
kernel and state-triggered governance services. It therefore behaves like a
document-driven microkernel:

| Repository element | Runtime responsibility |
|---|---|
| `GIT_AGENTS.md` | Portable, thin entrypoint and repository boundary |
| `ips-microkernel/work-router.md` | Minimal lifecycle dispatcher |
| `procedures/` | Bounded execution services invoked on demand |
| `references/` | Authority, safety, evidence, and live-state contracts |
| `selectors/` | Signal-to-destination decisions |
| `knowledge/` | Dormant knowledge modules expressed by matching signals |
| `exceptions/` | Special routes valid only under limited conditions |
| `scripts/check_docs.py` | Boundary inspector for roles, types, dependencies, reachability, and legacy-route restoration |

The term *microkernel* describes the architecture of responsibility and
loading. It does not claim literal operating-system process isolation, memory
protection, or hardware privilege levels.

## Reprogramming, differentiation, and expression

The iPS metaphor describes how a monolithic document set is transformed.

If an iPS cell represents a differentiated cell being reprogrammed to recover
other possibilities, the iPS Microkernel represents a large, undifferentiated
body of documents and files being reprogrammed into explicit runtime roles.
Those roles then differentiate the available context according to the current
work state.

The system does not keep every capability active. It waits for a signal and
expresses only the matching module:

- express dependency knowledge when dependency evidence requires it;
- express recovery knowledge when a known failure signature appears;
- express invocation knowledge when a tool-entry boundary fails;
- express the Markdown-only exception only when its qualifying conditions are
  proved;
- express public-safety or authority references only when their boundaries are
  implicated.

In the metaphor:

- **reprogramming** turns a monolithic document collection into governed
  runtime roles;
- **differentiation** forms the context appropriate to the current state;
- **expression** activates the one capability selected by a concrete signal;
- **dormancy** keeps unrelated knowledge out of the working context.

The metaphor communicates the design. The enforceable vocabulary remains
precise: **route**, **select**, **load**, **activate**, **transition**,
**return**, **prove**, and **validate**.

## Two separate graphs

The repository deliberately maintains two different navigation graphs.

The **human navigation graph** explains the portfolio and makes this page
discoverable from the repository root README. A reader may explore the name,
metaphor, history, and architecture at will.

The **runtime governance graph** starts at `GIT_AGENTS.md` and reaches only
role-bearing routers, selectors, procedures, references, knowledge modules,
exceptions, and selected design indexes. This README has no runtime role or
rule marker, is not a route target, and may not be linked from inside the iPS
Microkernel tree.

`scripts/check_docs.py` enforces that separation. Verification fails if this
page acquires a runtime marker, enters the routed surface, or gains an inbound
link from anywhere other than the repository root README.

The result is intentional asymmetry:

- humans can discover the explanation;
- runtime agents do not pay its context cost.

## Origin

The architecture began with a practical constraint:

> Do not waste tokens.
>
> Therefore, do not make the agent read unnecessary information.
>
> Therefore, differentiate documents by role.
>
> Therefore, start with a thin router and express only the capability required
> by the current state.

That sequence turned progressive disclosure from a documentation preference
into a governance architecture.

The former name, **AIOS**, described the growing system as an operating layer,
but it was broad, collided with existing concepts and services, and did not
name the mechanism that made the system distinctive. The new name preserves
the operating-system insight while identifying the real core: intentional
non-loading, progressive disclosure, governed roles, and a thin dispatch
kernel.

The conclusion became the birth story:

> We did not want to waste tokens.
>
> So we stopped loading unnecessary information.
>
> So we differentiated documents by runtime role.
>
> So a thin router began expressing only the functions required by state.
>
> **AIOS became the iPS Microkernel.**

The accepted architecture decision is recorded in
[ADR-0013](adr/0013-name-ips-microkernel.md). Earlier ADRs retain the AIOS name
as immutable evidence of the system's evolution; they are history, not a
second live route.

---

## 日本語

> 人間向けのアーキテクチャー解説。このファイルはruntime roleを持たず、
> ルーティングされたガバナンスグラフから意図的に除外されている。

このページはアーキテクチャーを説明するが、そのruntimeには参加しない。
iPS Microkernelを通じて動作するAIエージェントは、`GIT_AGENTS.md`から開始し、
薄いwork routerに従い、現在の状態に対して選択された経路だけをロードしなければ
ならない。この誕生物語を事前にロードしてはならない。機械的な文書検査がこの
ファイルを検査することはあるが、この物語がエージェントの作業コンテキストに
入ることはない。

このリポジトリで公開する製品の主軸は、引き続き
[Document Intelligence and Human Review Platform](../README.md)である。
iPS Microkernelは、その製品を設計、実装、レビュー、検証し、進化させるための
文書駆動ガバナンスアーキテクチャーである。両者のアイデンティティーを分ける
ことで、ルートREADMEは製品を主役にしたまま、このページにはアーキテクチャーの
思想と誕生の経緯を残すことができる。

### 名称

**iPS Microkernel**は、次の語を展開した名称である。

> **intentional Progressive-disclosure System Microkernel**

小文字の`i`、大文字の`P`と`S`は意図的な表記である。この名称は、iPS細胞で
親しまれている表記と、その背景にある製品名を意識した命名の物語に着想を得て
いる。同時に、各単語がアーキテクチャー上の制約を表す技術的な頭字語でもある。

#### intentional

**読まないことは設計判断である。**

無関係な文書をロードしないことは、コンテキストの欠落でも、不完全な初期化でも、
エージェントの失敗でもない。現在の作業に必要のない情報を、意図的にロードしない
のである。このシステムは、トークン、注意力、判断対象の広さを、有限のruntime
resourceとして扱う。

これにより、統治上の問いは次のように変わる。

> 事前にロードしておけば役に立つかもしれないものは何か。

ではなく、

> 現在の状態によって、今必要であると証明されたものは何か。

である。

#### Progressive-disclosure

すべての運用知識を起動時に開示することはしない。現在の状態が選択したrouter、
procedure、reference、knowledge、exceptionだけを段階的に開示する。

通常の作業は薄いrouterから始まる。具体的なsignalが発生すると、次に必要な
機能を一つだけ開示する。

- 焦点が定まっていない変更は、focus procedureを開示する。
- 受理済みIssueとbranchは、implementation procedureを開示する。
- 完全にstageされた候補は、CI routerを開示する。
- 権限境界に争点がある場合は、authority referenceを開示する。
- dependency failureは、dependency knowledgeを開示する。
- 条件を満たしたMarkdown-only変更は、そのexceptionを開示する。

選択されなかった兄弟要素は休眠したままである。開示は一度に一つの明示的な
transitionだけを進み、選択された処理によって状態が変化した後、呼び出し元へ
戻る。

#### System

これは、単にMarkdownファイルをきれいに整理したものではない。

これらの文書は、次の要素を持つガバナンスシステムを形成する。

- 明示的なruntime role
- 状態に基づくrouteとtransition
- canonical rule owner
- authorityとsafetyの境界
- inputとreturnが定義されたprocedure
- evidence requirement
- exceptionの適用条件
- dependencyとreachabilityの制約
- topology全体に対する実行可能な検査

文章は契約を伝える。path、marker、link、inventory、testは、その契約の重要な
部分を機械からも観測できる形にする。

#### Microkernel

起動時に保持するのは、最小のdispatch layerだけである。巨大な知識、特殊事例、
詳細なprocedureはkernelの外側に置き、選択された時だけロードする。

このアーキテクチャーは、常時ロードされるモノリシックなpromptを、薄いrouting
kernelと、状態によって起動するgovernance serviceへ置き換える。このため、
文書駆動microkernelとして振る舞う。

| リポジトリ要素 | runtime上の責務 |
|---|---|
| `GIT_AGENTS.md` | portableで薄いentrypointとリポジトリ境界 |
| `ips-microkernel/work-router.md` | 最小のlifecycle dispatcher |
| `procedures/` | 必要時に呼び出される、境界の明確な実行service |
| `references/` | authority、safety、evidence、live-stateの基礎契約 |
| `selectors/` | signalからdestinationへの選択 |
| `knowledge/` | 対応するsignalによって発現する休眠knowledge module |
| `exceptions/` | 限定条件下だけで有効になる特殊経路 |
| `scripts/check_docs.py` | role、型、dependency、reachability、旧経路復活を検査する境界検査器 |

*Microkernel*という語が表すのは、責務とロード方式のアーキテクチャーである。
OSが持つ文字どおりのprocess isolation、memory protection、hardware privilege
levelを備えていると主張するものではない。

### 再プログラム、分化、発現

iPSの比喩は、モノリシックな文書群をどのように変換するかを表している。

iPS細胞が、分化済みの細胞を再プログラムして別の可能性を開くものなら、
iPS Microkernelは、巨大で未分化な文書群・ファイル群を、明示的なruntime
roleへ再プログラムする。そのroleは、現在の作業状態に応じたコンテキストへ
分化する。

すべての機能を常に活動させることはしない。signalを待ち、それに対応する
moduleだけを発現させる。

- dependency evidenceが必要とした時、dependency knowledgeを発現させる。
- 既知のfailure signatureが現れた時、recovery knowledgeを発現させる。
- tool entryの境界が失敗した時、invocation knowledgeを発現させる。
- 適用条件が証明された時だけ、Markdown-only exceptionを発現させる。
- public safetyやauthorityの境界が関係する時だけ、そのreferenceを発現させる。

この比喩において、

- **再プログラム**は、モノリシックな文書群を、統治されたruntime roleへ
  変換する。
- **分化**は、現在の状態に適したコンテキストを形成する。
- **発現**は、具体的なsignalが選択した一つの機能を起動する。
- **休眠**は、無関係なknowledgeを作業コンテキストの外に保つ。

比喩は設計思想を伝える。一方で、検査可能な仕様語には、**route**、**select**、
**load**、**activate**、**transition**、**return**、**prove**、**validate**を
使用する。

### 分離された二つのグラフ

このリポジトリは、意図的に二つの異なるnavigation graphを持つ。

**human navigation graph**はポートフォリオを説明し、リポジトリのルートREADME
からこのページを発見可能にする。人間は名称、比喩、歴史、アーキテクチャーを
自由に読むことができる。

**runtime governance graph**は`GIT_AGENTS.md`から始まり、runtime roleを持つ
router、selector、procedure、reference、knowledge module、exception、および
選択されたdesign indexだけへ到達する。このREADMEはruntime roleやrule markerを
持たず、route targetではなく、iPS Microkernel treeの内部からlinkすることも
できない。

`scripts/check_docs.py`がこの分離を強制する。このページにruntime markerが
追加された場合、routed surfaceへ入った場合、またはリポジトリのルートREADME
以外からinbound linkが追加された場合、検証は失敗する。

その結果、意図的な非対称性が生まれる。

- 人間は説明を発見できる。
- runtime agentは、そのコンテキストコストを支払わない。

### 誕生

このアーキテクチャーは、実用上の制約から始まった。

> トークンを無駄にしない。
>
> そのため、不要な情報をエージェントに読ませない。
>
> そのため、文書を役割別に分化させる。
>
> そのため、薄いrouterから始め、現在の状態が必要とする機能だけを発現させる。

この連鎖によって、progressive disclosureは文書整理上の好みではなく、
ガバナンスアーキテクチャーとなった。

旧名称の**AIOS**は、成長したシステムをoperating layerとして表していた。
しかし、その意味は広く、既存の概念やservice名と衝突し、このシステムを
特徴づける仕組みそのものを表してはいなかった。新しい名称は、operating
systemとしての洞察を残しつつ、真の核心を名指す。すなわち、意図的な
non-loading、progressive disclosure、統治されたrole、薄いdispatch kernel
である。

そして、次の誕生物語へ至った。

> トークンを無駄にしたくない。
>
> だから不要な情報を読ませない。
>
> だから文書を役割別に分化させる。
>
> だから薄いrouterから必要な機能だけを発現させる。
>
> **その結果、AIOSはiPS Microkernelとなった。**

このアーキテクチャー決定は
[ADR-0013](adr/0013-name-ips-microkernel.md)に記録されている。それ以前の
ADRに残るAIOSという名称は、システムが進化した証拠として変更せず保持する。
それらは歴史であり、第二のlive routeではない。
