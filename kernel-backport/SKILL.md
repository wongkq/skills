---
name: kernel-backport
description: Methodology for backporting upstream Linux kernel features (subsystems, drivers, schedulers, BPF helpers) to older LTS bases — e.g., v6.12 → v6.6, v6.6 → v5.15, v5.10 → v4.19. Use this skill whenever the user asks to backport, port, or cherry-pick a kernel feature across major versions; when working on a long cherry-pick chain (10+ commits); when resolving conflicts between an upstream commit and an older base tree; or when the user mentions LTS, mainline, stable, downstream kernel, vendor kernel, or out-of-tree features needing to land on an older release. Also trigger when the user is debugging build failures during such a backport (missing symbols, struct field mismatches, signature divergence). The skill enforces an "upstream-first, no hand-written code" discipline that prevents the vendor-fork trap, defines a narrow controlled exception for verbatim manual fixups, and provides a state-persistence pattern that survives multi-day / multi-session work.
---

# Kernel Feature Backport

This skill captures hard-won methodology for backporting Linux kernel features from a newer upstream version to an older base (typically an LTS). It is opinionated because the failure mode it prevents is severe: writing stubs and sed-adapting calls to make the build pass produces a "working" kernel that has silently forked from upstream and can never re-sync.

The skill was distilled from a successful v6.12 → v6.6 sched_ext backport (117 cherry-picks + 10 controlled fixups landed cleanly, after a first attempt down the stub/sed/Makefile-bypass path failed). See `references/case-study-sched-ext.md` for the full case study.

## When this skill applies

Apply this skill whenever the work involves taking a feature that exists in a newer kernel tree and making it work on an older one, *and* the gap is larger than a few backportable commits. Symptoms that this is the right skill:

- The feature touches multiple subsystems (e.g., sched + BPF + cgroup)
- A naive cherry-pick of the "main" commit fails with missing symbols, fields, or macros
- The dependency closure is unclear at the start
- The work will span multiple sessions

If the work is just applying a single backport patch with a known fix, skip this skill — it is for the messy, exploratory, multi-week kind.

## The bedrock rule

**Every line of code in the final tree must trace to a specific upstream commit.** Either:

1. it came from a `git cherry-pick <upstream-hash>` (the normal case), or
2. it came from a `fixup:` commit whose body is a verbatim copy from a named upstream commit (the controlled exception, see below).

Hand-written code that has no upstream provenance is forbidden, no matter how small, no matter how obvious the fix seems.

### Why this is non-negotiable

The temptation in the moment is overwhelming: build fails because some BPF kfunc has a slightly different signature in v6.6, you sed the call site, build passes, move on. Repeated across 50 small adaptations, the result is a tree that:

- can no longer cherry-pick any upstream fix that touches the adapted code, because the adapted version has drifted
- has no commit-level traceability — `git blame` returns "manual adaptation" with no commit hash to compare against
- accumulates correctness risk: every "obviously equivalent" rewrite is a place where you might have subtly broken semantics

The vendor-fork outcome looks like success (vmlinux links! it boots!) but is structurally a dead end. A previous attempt on this exact project reached "vmlinux links cleanly at 406MB" with 9 files containing non-upstream code — and was thrown away in its entirety.

## Forbidden actions (explicit list)

Do **not** do any of these, ever, even for "just one line":

- Write stub functions (including `WARN_ONCE; return 0;` placeholders to make the linker happy)
- Use `sed` or hand edits to adapt call sites to match a different API signature
- Comment out subsystems in Makefiles or Kconfig to avoid compile errors
- Replace upstream calls with your own inferred "v6.6 equivalent"
- Hand-edit a file to revert code (use `git revert <upstream-hash>` instead)
- Plug placeholder values (NULL, 0, PAGE_SIZE) into new parameters without an upstream commit that did so
- Copy-paste upstream function bodies into a local file (use `git cherry-pick`)

"Small adaptation" is also a violation. "Just sed once" is also a violation. "Semantics are the same anyway" is also a violation. The rule has no soft edges because every soft edge gets exploited under deadline pressure.

## The cherry-pick driven loop

This is the only correct way to make forward progress. Run it as a tight loop, not as a planning exercise.

```
1. Cherry-pick the commit you currently want.
2. Build. Look at the FIRST error only.
3. Identify the missing symbol / field / macro.
4. git log --all -S<symbol>  →  find the upstream commit that introduced it.
5. Cherry-pick that commit (recursing into step 2 if it also fails).
6. Repeat until the original commit builds.
```

The single most common mistake — *especially* when working with an LLM — is trying to predict the full dependency closure up front. Don't. Predicted closures are routinely off by an order of magnitude (sched_ext backport: predicted "20-30 prereq commits", actual: 117). The build error tells you exactly what you need next; trust it.

When this skill is in effect, suppress the urge to draw dependency graphs, write planning docs, or estimate "how many commits will this take". Just run the loop.

### Conflict resolution: what's allowed

Cross-major-version cherry-picks frequently conflict not because of real semantic divergence, but because of line offsets and context drift. These mechanical conflicts may be resolved manually, with this constraint:

- Both sides of the conflict must come from upstream (HEAD contains prior cherry-picks or the base; the in-flight commit is upstream).
- The resolution places the upstream hunk in the right spot in the older tree. No new logic is introduced.
- Prefer mechanical tools first: `git checkout --theirs/--ours`, `git cherry-pick -X theirs`, `git am --3way --fuzz=N`.
- If you hand-edit, every line must trace to a specific upstream commit's specific line.

If a conflict represents a real semantic gap (not line drift), it is a missing-prereq signal. Abort the cherry-pick, find the upstream commit that bridges the gap, pick it, then retry the original. Abort + retry is the correct workflow. Do not "just resolve" a semantic conflict by guessing.

## Controlled fixup exception

Some cases genuinely cannot be solved by cherry-picking more commits:

1. **Treewide upstream commits.** A single upstream commit changes thousands of files (e.g., a tracing macro signature change across the whole tree). Cherry-picking it brings massive unrelated churn. You only need one file's adaptation.
2. **API signature split across commits.** The caller and the implementation of a new signature live in different upstream commits. After picking the caller commit, the build can't link until the implementation commit lands, but that may be far down the chain.
3. **`-X ours` artifacts.** A previous conflict resolution dropped a few lines that a later commit then expects to be present.

For these, a narrow exception exists: write a commit whose subject starts with `fixup:` containing the missing adaptation. The rules:

- Every line must be **verbatim copied** from a named upstream commit. Not paraphrased, not "v6.6 equivalent", not "obviously same idea" — literally `git show <hash> -- <file>` and copy the relevant block.
- The commit message lists every source upstream commit hash. This is non-negotiable; the hash is how a future engineer (or future you) verifies the fixup is still legitimate, and how a future upstream commit may eventually replace it.
- No new logic. No stubs. No sed-style mass rewrites.
- The fixup should be isolated and self-contained, so that if some future upstream commit makes it redundant, it can be cleanly dropped.

If a single fixup exceeds ~50 lines or spans many unrelated changes, stop. That's a signal you missed an upstream prereq commit. Go back to the cherry-pick loop and find the prereq instead of expanding the fixup.

For a worked example showing what these fixups look like in practice, see `references/case-study-sched-ext.md`.

## When the loop fails to converge

Sometimes the dependency closure genuinely explodes — every cherry-pick reveals five new prereqs, each of which reveals five more. When this happens:

1. **Stop.**
2. Report concretely: which commit you're stuck on, what symbol/field is missing, what cherry-pick chain you've already done.
3. Wait for the user to decide direction. Options they may pick:
   - Drop the feature from this base
   - Switch to a vendor-fork strategy (with clear-eyed understanding of the cost)
   - Pick a different feature subset to backport
   - Move to a newer base

**Never** silently switch to writing stubs / sed-adapting / commenting out Makefiles as a way to "keep moving". The user explicitly asked for upstream-traceable code; if that becomes impossible, the right action is to surface it, not to quietly trade it away for apparent progress.

## State persistence across sessions

This work routinely spans multiple sessions. Treat conversation memory as unreliable; persist everything in git.

**End of each day**: tag the current HEAD with a checkpoint name like `session-<topic>-checkpoint-day<N>-<milestone>`. This gives every session a known-good restart point.

**A CLAUDE.md "Current progress" section**: keep it updated with:
- The current HEAD commit hash
- The latest checkpoint tag
- Build status of the relevant configs
- What the next stage is (so a new session can pick up without re-deriving everything)
- Any partial-cherry-pick or in-flight conflict state

**Start of each new session**: before any work, verify the state. Read CLAUDE.md's progress section, run `git status -s` (expect clean), `git log -1 --oneline` (expect to be on the recorded HEAD), `git tag -l | tail` (expect the recorded checkpoint).

If reality and the recorded state diverge, **stop and reconcile** before doing anything else. Don't start cherry-picking on a base you don't fully understand.

## Common LLM failure modes to suppress

When this skill is loaded, actively suppress these LLM tendencies — they look helpful but produce vendor-fork drift:

1. **"Let me write a small stub to make the linker happy."** No. Find the upstream commit that defines the symbol.

2. **"I'll infer the v6.6 equivalent of this v6.12 API."** No. The inference will be wrong in ways that don't show up at build time. Find the actual upstream commit that introduces or modifies the API.

3. **"I'll sed all the callers to match the old signature."** No. Either cherry-pick the commit that changes the signature, or write a verbatim fixup if it's a treewide-change case.

4. **"This Makefile entry is causing trouble; let me comment it out for now."** No. Comments-out are a form of hand-written code without provenance. Either pick the commit that legitimately disables it, or solve the underlying dependency.

5. **"Let me plan out the next 20 commits I'll need before starting."** No. Run the cherry-pick loop. The plan will be wrong; the build will guide you correctly.

6. **"The build passes now, success."** Not until you've grepped the diff for hand-written changes. After any session of work, run `git log <base>..HEAD` and confirm every non-cherry-pick commit is a `fixup:` with valid upstream provenance in its message.

These failure modes are not abstract — every one of them happened during the first failed attempt of the sched_ext project. The skill exists specifically to suppress them.

## Quick reference: workflow per cherry-pick

```bash
# 1. Try to pick
git cherry-pick <upstream-hash>

# 2. If conflict: is it line-offset (mechanical) or semantic?
#    Mechanical: resolve in place, every line traceable to upstream.
#    Semantic:   git cherry-pick --abort, find prereq, pick prereq, retry.

# 3. Build
make -j$(nproc) <target>

# 4. Build failure?
#    First error → identify missing symbol → find upstream commit:
git log --all -S'<symbol>' --oneline | head

# 5. Pick the prereq commit, recurse on step 3.

# 6. Build passes:
#    Save state, consider a checkpoint tag if at a stable milestone.
```

## Quick reference: when you're tempted to hand-write

Ask yourself:

- **Is there an upstream commit that does this?** If yes, pick it. Always.
- **Is this a treewide-change adaptation?** If yes, a `fixup:` commit with verbatim copy from the upstream commit is allowed. List the source hash.
- **Is this a signature-split artifact?** Same — verbatim fixup, list source hash.
- **Am I rewriting because "it's faster"?** Stop. That is the vendor-fork trap.
- **Has my fixup grown past ~50 lines?** Stop. You missed a prereq. Find it.

## Further reading

- `references/case-study-sched-ext.md` — full worked example: 117 cherry-picks + 10 fixups, where each fixup came from, how conflict resolution played out across the BPF subsystem, what the failed first attempt looked like
- `references/conflict-playbook.md` — concrete recipes for the conflict patterns that recur in cross-version backports
