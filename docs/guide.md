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

What it does not do, yet: run a real model, touch a GPU, quantize anything,
or arbitrate between two agents who both want the same chip. What it will
never do, by design: let the thing submitting the work decide whether the
rules apply to it.

## Try the proof yourself

Three commands, no downloads, nothing leaves your machine:

```sh
python3 -m venv .venv
.venv/bin/python prove.py
```

That runs the test suite — the original twelve tests, five more for the
Phase 1 contracts, and six for Phase 2's discovery, estimates, and scoring
— and regenerates the evidence folder: the same numbers quoted above,
produced on your hardware instead. If they don't match, that's a finding,
and findings are the point.

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
behaves like a protocol instead of a hope. Then quantization whose quality is
*measured* against a reference — or labeled, in plain text, "unmeasured."
Then a second backend, which is the real exam: if adding a GPU means changing
the parts that talk to applications, the design was leaking all along. And
last, the receipts and the ledger, so that anything an agent does inside this
runtime can be answered for afterward.

One thin path, proved at every step, with the failures written down next to
the successes. If you've read the rest of Substrate Research's record, that
method will sound familiar. It's the same institute, pointed at a different
environment: not the world a model learns in, but the machine it wakes up on.
