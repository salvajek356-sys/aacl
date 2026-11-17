# The Compatibility Layer — a reader's guide

![The stationmaster: a small robot with a request ticket, a board of gauges, a gate, and three very different engines — one of them across the chasm, one track broken in the foreground.](accl-panel.jpg)

*What AACL is, why it exists, and where it honestly stands. Written to be read,
not just audited.*

## The problem, in one story

Every program that runs a model wakes up on a different machine. One has a big
graphics card and no memory to spare; the next is a modest laptop chip that
sips power; a third is a server across the country that you're not allowed to
send your data to. Today, the program is expected to know all of this in
advance — which hardware, which precision, which limits — and to be rewritten
when any of it changes.

That is backwards. The program should be able to say what it *needs* — "this
result, this fast, in this much memory, and my data stays on this machine" —
and the machine should introduce itself honestly: what it can do, what it
can't, and what it has actually managed lately. Somewhere between the two,
something has to make a decision it can explain.

That something is the Agentic Acceleration Compatibility Layer. AACL, or ACCL
if you're reading the older documents — the name wobbled before the idea did.

## What it does with a request

A request arrives as a **WorkloadSpec**: the job, stated as requirements
rather than instructions. Then, in order:

1. **Discovery.** The runtime asks each backend what it can genuinely do —
   architecture, precisions, memory, which operations really run — and writes
   it in a capability registry. Claims are recorded as claims.
2. **Candidates.** For each backend that might fit, the planner sketches a
   possible way to run the job: this chip, this precision, this artifact.
3. **The gate.** Candidates are filtered twice, and the order matters. First
   hard constraints — a plan that can't fit in memory is not a plan. Then
   policy — a plan that would send local-only data to a remote machine is
   forbidden, and no score, however fast, is allowed to make a forbidden plan
   look attractive.
4. **The choice.** Survivors are scored by *target pressure*: how close each
   one comes to breaking the tightest promise the workload itself made. The
   winner comes with a sentence a person can read — "chosen because it sits at
   62% of its latency budget" — not a number nobody can explain.
5. **Execution, with a way back.** If the chosen plan fails, the executor
   doesn't improvise. The plan carries its ranked alternatives with it, each
   attempt re-passes the policy gate, and a backend that claimed it could do
   something it couldn't gets its reliability marked down in the registry.
   Execution is the experiment; the registry keeps score.
6. **Telemetry.** Every run is recorded — what was asked, what was chosen,
   what happened, how long each part took. Not as a dashboard. As evidence.

And at the end of the road, when agents are the ones submitting work: a signed
**receipt** for every execution, so an agent can prove to whoever trusted it
exactly what ran, where, on what data, and why that plan — while never being
able to override the rules itself. Trust without control. That phrase is the
whole endgame.

## Where it honestly stands

This is a young project, and this guide will not pretend otherwise.

- **On paper, it's finished twice.** A roadmap (*From Concept to Working
  Runtime*) lays out the build in milestones. A companion (*Finishing the
  Thought Experiment*) then argues with the roadmap — replaces its scoring
  math, its fallback story, its missing pieces — and extends it two milestones
  further. The argument is part of the record, on purpose.
- **In code, it's a proof, deliberately tiny.** The v0.1 proof runs the whole
  path — normalize, discover, plan, gate, execute, record, respond — for one
  small hand-built model on an ordinary CPU. Twelve tests, all passing, with
  the evidence saved. It proves the *pipe*, not performance: no graphics card,
  no real acceleration, no quantization yet. Its own README says so, in a
  section titled "What this proves (and does not)."
- **As of 16 November 2026**, the proof has been moved, piece by piece, into
  the package layout the roadmap specifies — and the move was verified the
  only way that counts: the original tests, unmodified, still pass, and the
  proof's measurements reproduce its September evidence to the last digit.
  That is Phase 0 of the build plan. The contracts grow teeth in Phase 1.
- **As of 17 November 2026**, the contracts have their first teeth — Phase 1.
  A request can now say what it *wants*, not just what it is: a latency
  target, a memory limit, a cost budget, which of those to optimize for, and
  the name of the reference its quality should one day be judged against.
  Say any of it wrong — a negative budget, an optimization nobody offers —
  and the refusal arrives in writing, as before. Say it right, and the words
  are carried into the plan and repeated back in its explanation. But read
  the explanation closely, because it says the quiet part out loud: the
  targets are *recorded*, not yet *scored*. Choosing by them is Phase 2's
  work, and this phase declines to pretend otherwise. Underneath, two
  quieter changes. Execution now travels through a handle — the shape a
  slow or distant machine will need — even though the CPU backend finishes
  before the handle is handed back, and says so when you try to cancel it:
  nothing was stopped, because nothing was still running. And every artifact
  has a full name now — which model, from what source, at what precision,
  under what transformation, for which backend, hashed together — so two
  artifacts with the same name are the same artifact. Every response also
  carries a receipt, unsigned and labeled unsigned in plain sight: the shape
  of the promise the endgame will keep, not the promise itself.
- **Later on 17 November 2026**, the planner started making real decisions —
  Phase 2. Two changes underneath. First, the machine's introduction of
  itself is no longer written in advance: when the runtime starts, it reads
  the machine it woke up on — how many cores it may use, how much memory
  there is and how much is free, how large a cache it may keep — and writes
  down what it found. Second, the choice itself. Each surviving candidate
  now gets an estimate — latency, memory, cost — plainly labeled an
  estimate, built from a small static model whose constants sit in one file
  where anyone can argue with them. The winner is the candidate whose worst
  pressure against the promises *you* made is lowest: declare a latency
  target tight enough, and the runtime chooses the narrower precision and
  tells you it sits at 76% of its latency budget while the wider one would
  have broken it at 124%. That sentence is the one this whole design was
  built to be able to say. Two honest limits remain, and the explanations
  state both. Quality is still not measured: name a reference and it is
  carried, named, and given no say in the choice until Phase 4 teaches the
  runtime to measure against it. And if a request declares no targets at
  all, there is nothing to score — the old standing preference decides, and
  the plan says that instead of inventing a pressure.
- **Later still on 17 November 2026**, fallback stopped being a hope and
  became a protocol — Phase 3. The plan no longer names a single winner and
  keeps its fingers crossed: it carries every survivor, ranked, and the
  executor walks that list in order. Each attempt re-passes the policy gate
  — a candidate the gate refuses at execution time is recorded as refused,
  never run — and each attempt is written down with a name for what
  happened. There are four names: a backend error, a timeout, a policy
  denial, and the interesting one, a *capability lie* — a backend that
  claimed it could do something and then, asked to do it, said no. A lie
  has a consequence: the registry marks that backend's claim down, and the
  next plan ranks it below the honest alternatives and says so in its
  explanation. Not a ban — a last resort, in case everything else is worse
  — but a memory. The test that proves it is a small act of theatre: a fake
  backend that advertises two precisions and lies about one of them. The
  first request falls back and succeeds anyway; the second never tries the
  liar first. Artifacts, meanwhile, got a household: a cache keyed by their
  full names, bounded by the cache ceiling discovery wrote down, evicting
  the least-recently-used when it fills — except the artifacts of a plan
  currently running, which are pinned until it lands.
- **Before the day was out on 17 November 2026**, the runtime learned to
  measure — Phase 4. Two arrivals. First, a real model: not hand-built this
  time but *trained* — a small classifier taught on the Iris dataset,
  Fisher's 150 rows from 1936, embedded in the repo so nothing is
  downloaded — by the plainest training there is, gradient descent under a
  frozen recipe. Anyone can retrain it and check: the weights that come out
  are the weights in the code, digit for digit. It names 29 of the 30
  held-out flowers correctly; the one it misses sits on the border between
  two species, where honest classifiers have always argued. Second,
  quantization stopped being a rumor. A transformation service takes the
  trained model, runs a reserved calibration slice of the same dataset,
  works out its scales, and produces an int8 artifact — integers all the
  way through the arithmetic, one honest multiply at the end. And quality
  became a measurement instead of a posture. Name the reference — the
  held-out slice has a name, *iris-eval-v1* — and every candidate's drift
  from the floating-point model is measured on it and written into the plan
  and the run's record: fp32's scores stray by about five ten-millionths on
  average; int8's by about five hundredths, worst row near two tenths.
  Neither flips a single label on this eval set, which is exactly why a
  workload's drift tolerance is reckoned in score error — the figure that
  actually moves. Declare a tolerance and quality joins the choosing as a
  fourth pressure: the same request that picks int8 when it may drift a
  tenth picks fp32 when it may drift only a hundredth. Declare no reference
  at all and the plan says, in the plan's exact words, *quality unmeasured —
  no reference.* One refusal grew sharper in the bargain: a reference name
  that doesn't exist is no longer carried politely. It is refused in
  writing, because a reference is now a thing that exists or doesn't.
- **And then, the same day, Phase 5 was built** — which is not the
  same as *run*, and this guide will keep the two words separate. The
  second backend exists now: a GPU backend that runs both models
  through PyTorch on an accelerator, behind the same handle contract,
  claiming only the precisions it can genuinely execute — the floating
  point pair, never int8. Its discovery is a probe, not a hope: the
  device is asked, small test multiplications are actually run on it,
  and only what demonstrably works is advertised. On a machine with no
  device — including the machine this was built on — discovery
  registers the CPU alone, no GPU candidate is ever generated, and the
  runtime behaves exactly as Phase 4 left it, byte for byte. Where a
  device does exist, the same planner, the same scorer, the same
  executor choose between the two backends per workload, from static
  estimates that now carry a GPU row — launch overhead and a device
  context honestly charged, bandwidth honestly credited — labeled
  placeholders until Phase 6 replaces estimates with measurements.
  And the exam itself was made mechanical: a script diffs the whole
  phase against Phase 4's commit and fails if anything outside a
  short, reasoned allow-list changed. The planner, the scorer, the
  executor, the policy gate, the telemetry shapes — byte-identical, or
  the audit says so. On the build machine, the audit passes. **What
  has not happened: the GPU run.** Nobody has watched this backend
  execute on real hardware yet. That session belongs to the Strix Halo
  in the corner of Tony's office, its pass criteria written down in
  advance in a runbook in this repo — suite green with the GPU tests
  actually running, audit passing, the planner choosing each backend
  at least once, the two backends' answers agreeing. Until that
  session happens and its output is pasted back, the honest status of
  Phase 5 is: built, audited, and unproven where it counts.
  *The session has since happened, and the sentence updates rather
  than stands.* On the Strix the exam's structural half passed
  outright — every protected file byte-identical on the real
  machine. The execution half never got to speak: the machine's
  PyTorch build crashed inside its own bundled runtime on the very
  first kernel, in three lines of pure PyTorch with none of this
  code present, and a controlled diagnosis — the same memory test
  against the system ROCm runtime, which passed completely — put
  the fault in the wheel's HSA layer, below the backend line
  entirely. Recorded as what it is: an environment finding, not a
  leak and not a pass. One flaw *was* this project's, and it is
  fixed: discovery once probed in-process, so a backend that
  crashed on contact killed the runtime it was only visiting. The
  probe now runs in a subprocess; on that same broken machine,
  discovery today reports no GPU and the CPU serves on — which is,
  in the end, the behavior a compatibility layer exists to have.
  *The session has since finished, and the sentence updates
  again.* A working torch was built in an isolated corner of the
  Strix — AMD's own 7.14.1-line successor build for this chip,
  installed without touching the broken one or the system ROCm —
  and under it the exam ran in full. The unchanged planner chose
  the GPU where the targets demanded it and the CPU where they
  didn't; the two backends' answers agreed to nothing at all on
  the demo model and to a millionth on the flower classifier,
  labels exact everywhere; and the proof, run from the repo root,
  reproduced its precision figures to the last digit. Phase 5's
  verdict, against the criteria written down before any of it
  ran: **PASS** — the second backend arrived, nothing above the
  backend line changed, and the device does the work correctly.
  The hardware runs earned one more entry in the record: they
  caught two bugs of this project's own, the same eagerly
  evaluated default hiding in both the agreement test and the
  demo — the kind of bug that only exists because a test had
  never run anywhere before. First executions are exams too.
  And the amendment met its own exam on the same machine: under
  the old broken python the suite now completes on the CPU
  instead of dying without a word.

What it does not do, yet: run anything larger than a flower
classifier, measure instead of estimate (Phase 6), or arbitrate
between two agents who both want the same chip. Nor does it run
on an NPU: the Strix's NPU stands enabled and compiler-ready as
a separate track (`docs/npu-enablement-strix.md`), with no
backend built.
What it will never do, by design: let the thing submitting the work decide
whether the rules apply to it.

## Try the proof yourself

Three commands, no downloads, nothing leaves your machine:

```sh
python3 -m venv .venv
.venv/bin/python prove.py
```

That runs the test suite — the original twelve tests, five more for the
Phase 1 contracts, six for Phase 2's discovery, estimates, and scoring, ten
for Phase 3's fallback protocol and artifact cache, eleven for Phase 4's
trained model, quantization, and measured drift, and nine for Phase 5's
second backend: six that run anywhere (discovery's honesty, routing,
the no-GPU properties) and three that run only on a machine with a GPU
genuinely in it — and regenerates
the evidence folder: the same numbers quoted above, produced on your
hardware instead. If they don't match, that's a finding, and findings are
the point.

To poke the API by hand:

```sh
.venv/bin/python -m aacl.api.service --port 8000
curl http://127.0.0.1:8000/infer -H 'Content-Type: application/json' \
  -d '{"model_id":"linear-demo-v1","input":[1,2,3,4],"local_only":true}'
```

Ask for `[1,2,3,4]` and you should get a score of 4.375 and label 1 — the
reference result the tests check. Then try forbidding things: set
`allowed_precisions` to `["int8"]` and watch the runtime refuse, in writing,
rather than quietly doing something else. That refusal is the product, in
miniature.

## The road ahead, in plain words

Contracts first, so invalid combinations get caught before they reach a
machine. Then a planner whose choices can be explained. Then fallback that
behaves like a protocol instead of a hope — built, and proved against a
backend that lies. Then quantization whose quality is
*measured* against a reference — built, with the measurement carried in the
plan — or labeled, in plain text, "unmeasured" when there is no reference to
measure against.
Then a second backend, which is the real exam: if adding a GPU means changing
the parts that talk to applications, the design was leaking all along. The
backend is built and the diff audit passes; the exam's last sitting is on
real hardware, with its criteria written down in advance.
And
last, the receipts and the ledger, so that anything an agent does inside this
runtime can be answered for afterward.

One thin path, proved at every step, with the failures written down next to
the successes. If you've read the rest of Substrate Research's record, that
method will sound familiar. It's the same institute, pointed at a different
environment: not the world a model learns in, but the machine it wakes up on.
