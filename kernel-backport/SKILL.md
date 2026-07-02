---
name: kernel-backport
description: Methodology for backporting Linux kernel features from newer upstream to older LTS bases (e.g., v6.12 → v6.6, v6.6 → v5.15, v5.10 → v4.19). Use when cherry-pick chain exceeds 10 commits; when the feature spans multiple subsystems (sched+BPF+cgroup, net+TLS, fs+VFS); when debugging backport build failures (missing symbols, struct field mismatches, signature divergence); or when working on vendor/downstream kernels. Enforces "upstream-first, no hand-written code" discipline, defines a narrow controlled exception for verbatim manual fixups, and provides a state-persistence pattern for multi-day / multi-session work. Supports strict and exploratory modes.
---

# Kernel Feature Backport

## 30-second summary

Backport Linux kernel features from newer upstream to older LTS base.
**Core rule: every line in your tree must trace to a specific upstream commit.**

- Pick upstream commits via `git cherry-pick`; don't write code
- Let build errors drive the chain — don't predict dependencies
- Conflicts: line drift (resolve) or semantic gap (abort + pick prereq)
- Allowed exception: `fixup:` commits with verbatim copy + upstream hash in body
- State persists in git (tags) + CLAUDE.md (progress section)

## When this skill applies

Apply whenever the work involves taking a feature that exists in a newer kernel
tree and making it work on an older one, *and* the gap is larger than a few
backportable commits. Symptoms that this is the right skill:

- The feature touches multiple subsystems (e.g., sched + BPF + cgroup)
- A naive cherry-pick of the "main" commit fails with missing symbols, fields, or macros
- The dependency closure is unclear at the start
- The work will span multiple sessions

If the work is just applying a single backport patch with a known fix, skip this
skill — it is for the messy, exploratory, multi-week kind.

## Bedrock rule

**Every line of code in the final tree must trace to a specific upstream commit.** Either:

1. it came from `git cherry-pick <upstream-hash>` (the normal case), or
2. it came from a `fixup:` commit whose body is verbatim copy from a named upstream commit (the controlled exception).

Hand-written code without upstream provenance is forbidden. "Small adaptation",
"just sed once", and "semantics are the same anyway" are not exemptions.
The vendor-fork failure mode looks like success (vmlinux links, kernel boots) but
is structurally a dead end.

A previous attempt on sched_ext reached "vmlinux links cleanly at 406MB" with 9
files containing non-upstream code. The result could no longer cherry-pick any
upstream fix touching those files; `git blame` returned "manual adaptation" with
no commit hash; semantic correctness was unrecoverable. The attempt was thrown
away in its entirety. Tag `session5-stubs-hardened` preserves it as a warning.
See `references/case-study-sched-ext.md#the-failed-first-attempt`.

## Bedrock rule exceptions (explicit opt-in)

The bedrock rule can be **explicitly relaxed** by the user for prototype or
exploration work. State in the prompt and record in CLAUDE.md:

```
Mode: exploratory
```

In exploratory mode:

- `fixup:` requirement is relaxed to "best effort upstream traceable"
- Stubs are allowed BUT tagged `// EXPLORATORY: stub, to be replaced`
- Session-end `git log <base>..HEAD` verification is still mandatory
- Switching back to strict mode requires fresh commit history (no carry-over)

## Forbidden actions (no soft edges)

- **Stubs**: `WARN_ONCE; return 0;` or any placeholder to make the linker happy
- **sed-adapting**: rewriting call sites to match a different API signature
- **Commenting out**: disabling Makefile/Kconfig entries to avoid compile errors
- **Inference**: replacing upstream calls with your guessed "older equivalent"
- **Manual revert**: hand-editing to revert code (use `git revert <hash>` instead)
- **Placeholder params**: plugging `NULL`/`0`/`PAGE_SIZE` without upstream provenance
- **Copy-paste**: copying upstream function bodies into local files (use `git cherry-pick`)

For the cautionary anchor of what these produce in aggregate, see
`references/case-study-sched-ext.md#anti-patterns-observed-in-the-failed-attempt`.

## The cherry-pick driven loop

This is the only correct way to make forward progress. Run it as a tight loop,
not as a planning exercise.

```
1. git cherry-pick <upstream-hash>
2. Build. Look at the FIRST error only.
3. Identify the missing symbol / field / macro.
4. git log --all -S<symbol> --oneline  →  find the upstream commit that introduced it.
5. Cherry-pick that commit. Record it in CLAUDE.md's "Visited prereqs" list.
   If the commit is already in "Visited prereqs" → STOP — circular dependency.
   Surface to user instead of looping.
6. Repeat from step 2 until the original commit builds.
```

Trust build errors. Predicted closures are routinely off by an order of magnitude
(sched_ext: predicted 20-30 prereqs, actual 117). Suppress the urge to draw
dependency graphs, write planning docs, or estimate "how many commits will this
take". Just run the loop.

## Conflict triage

```
            cherry-pick conflict?
                    │
        ┌───────────┴───────────┐
   upstream code is         upstream code references
   recognizable,            symbol/field/macro that
   just shifted?            does not exist in HEAD?
        │                           │
   LINE DRIFT                  SEMANTIC GAP
   resolve in place            ABORT cherry-pick
   (each line traces           git log -S<missing>
    to one side)               pick the prereq first
                               then retry
```

Mechanical tools first: `git checkout --theirs/--ours`, `git cherry-pick -X theirs`,
`git am --3way --fuzz=N`. If you hand-edit, every line must trace to a specific
upstream commit's specific line — treat it as an implicit `fixup:` and add the
source hash to the commit message.

If a conflict represents a real semantic gap (not line drift), abort the
cherry-pick, find the upstream commit that bridges the gap, pick it, then retry.
Do not "just resolve" a semantic conflict by guessing.

For 7 recurring conflict patterns with concrete recipes, see
`references/conflict-playbook.md`.

## Controlled fixup exception

Some cases genuinely cannot be solved by cherry-picking more commits:

1. **Cascade cap.** Source commit requires picking 5+ unrelated commits you don't need.
2. **Treewide upstream change.** A single upstream commit changes thousands of files; you only need one file's adaptation.
3. **API signature split.** Caller and implementation of a new signature live in different upstream commits, and the dependency graph forces one to be picked far ahead of the other.

For these, write a commit whose subject starts with `fixup:` containing the
missing adaptation. Rules:

- Every line **verbatim** copied from `git show <hash> -- <file>` — not paraphrased, not "v6.6 equivalent", literally the upstream block.
- The commit message lists every source upstream commit hash. Non-negotiable: the hash is how a future engineer verifies the fixup is still legitimate, and how a future upstream commit may eventually replace it.
- No new logic. No stubs. No sed-style mass rewrites.
- **Hard cap: 50 lines net change, 5 files.** Larger → you missed a prereq. Go back to the cherry-pick loop.
- Isolated and self-contained so a future upstream commit can drop it cleanly.

For a worked example showing what these fixups look like in practice, see
`references/case-study-sched-ext.md#the-10-fixup-commits-in-detail`.

## When the loop fails to converge

Sometimes the dependency closure genuinely explodes — every cherry-pick reveals
five new prereqs, each of which reveals five more. When this happens:

1. **Stop.**
2. **Batch report** (don't interrupt per-gap): list all stuck commits, missing symbols, and chain so far in a single message. If >2 consecutive semantic gaps are of the same type, accumulate them.
3. Wait for the user to decide direction:
   - Drop the feature from this base
   - Switch to a vendor-fork strategy (with clear-eyed understanding of the cost)
   - Pick a different feature subset to backport
   - Move to a newer base
4. If user explicitly set `Mode: exploratory` in CLAUDE.md, the bedrock rule is relaxed — proceed under that mode instead.

**Never** silently switch to writing stubs / sed-adapting / commenting out
Makefiles as a way to "keep moving". The user explicitly asked for
upstream-traceable code; if that becomes impossible, surface it.

## State persistence across sessions

This work routinely spans multiple sessions. Treat conversation memory as
unreliable; persist everything in git.

**End of each day**: tag the current HEAD with a checkpoint name like
`session-<topic>-checkpoint-day<N>-<milestone>`. This gives every session a
known-good restart point.

**CLAUDE.md "Current progress" section** must keep updated with:

- HEAD commit hash
- Latest checkpoint tag
- Build status of relevant configs
- Next stage description (so a new session can pick up without re-deriving)
- Any in-flight cherry-pick or conflict state
- **Visited prereqs list** (for circular dependency detection)

**Start of each new session**: before any work, verify the state.

```bash
git status -s                # expect clean
git log -1 --oneline         # expect matches CLAUDE.md HEAD
git tag -l | tail -1         # expect matches CLAUDE.md checkpoint
```

If reality and the recorded state diverge, **stop and reconcile** before doing
anything else. Don't start cherry-picking on a base you don't fully understand.

### CLAUDE.md progress template

```markdown
## Current progress: kernel-backport [<feature>]

- **Mode**: strict | exploratory
- **Base**: <LTS-tag-or-commit>
- **Source range**: <upstream-tag-range>
- **HEAD**: <commit-hash>
- **Last checkpoint tag**: <tag-name>
- **Build status**:
  - `<config1>`: ✓ clean | ✗ <error-summary>
  - `<config2>`: not yet attempted
- **Next stage**: <what-to-do-next>
- **In-flight**: <any pending cherry-pick / conflict>
- **Visited prereqs**: <commit-hash-list>
```

## Per-subsystem patterns

| Subsystem        | Typical cascade | Key conflict              | Strategy                                                            |
| ---------------- | --------------- | ------------------------- | ------------------------------------------------------------------- |
| Drivers          | 1-3 commits     | Makefile / Kconfig        | Skip this skill (too small)                                         |
| FS / VFS         | 5-15 commits    | struct field additions    | Prefer `linux-stable` cherry-picks (smaller, vetted)                |
| Networking       | 20-40 commits   | `tcp_sock` ABI gaps       | Use `fixup:` for new fields with explicit init from upstream commit  |
| BPF / scheduler  | 50-200 commits  | deep CFI / verifier chain | sched_ext case study is the canonical worked example                |

## LLM failure modes to suppress

When this skill is loaded, actively suppress these LLM tendencies — they look
helpful but produce vendor-fork drift. Each one happened during the first failed
attempt of the sched_ext project.

1. **"Let me write a small stub to make the linker happy."** No. Find the upstream commit that defines the symbol.
2. **"I'll infer the v6.6 equivalent of this v6.12 API."** No. The inference will be wrong in ways that don't show up at build time. Find the actual upstream commit that introduces or modifies the API.
3. **"I'll sed all the callers to match the old signature."** No. Either cherry-pick the commit that changes the signature, or write a verbatim fixup if it's a treewide-change case.
4. **"This Makefile entry is causing trouble; let me comment it out for now."** No. Comments-out are a form of hand-written code without provenance. Either pick the commit that legitimately disables it, or solve the underlying dependency.
5. **"Let me plan out the next 20 commits I'll need before starting."** No. Run the cherry-pick loop. The plan will be wrong; the build will guide you correctly.
6. **"The build passes now, success."** Not until you've grepped the diff for hand-written changes. Run session-end verification (below) after every session.

## CI integration (recommended)

`.github/workflows/backport-verify.yml`:

```yaml
name: backport-verify
on: [push]
jobs:
  provenance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Check no hand-written code
        run: |
          for commit in $(git rev-list <base>..HEAD); do
            subject=$(git log -1 --format=%s $commit)
            body=$(git log -1 --format=%b $commit)
            if echo "$subject" | grep -qE "^fixup:"; then
              if ! echo "$body" | grep -qE "cherry picked from commit [0-9a-f]{40}"; then
                echo "ERROR: $commit fixup: missing upstream hash in body"
                exit 1
              fi
            fi
          done
```

## Session-end verification (mandatory)

After every session of work, run:

```bash
git log <base>..HEAD --oneline | grep -v 'cherry picked' | grep -v '^fixup:'
```

Expect: empty. Any non-cherry-pick / non-fixup commit is a violation. Investigate
before continuing.

## Quick reference: workflow per cherry-pick

```bash
# 1. Try to pick
git cherry-pick <upstream-hash>

# 2. If conflict: is it line drift or semantic gap?
#    Line drift: resolve in place, every line traceable to upstream
#    Semantic gap: git cherry-pick --abort, find prereq, pick prereq, retry
git cherry-pick --abort

# 3. Build
make -j$(nproc) <target>               # macOS: $(sysctl -n hw.ncpu)

# 4. Build failure → first error → identify missing symbol
git log --all -S'<symbol>' --oneline | head

# 5. Pick prereq, recurse from step 3

# 6. Build passes → save state, checkpoint tag if at milestone
git tag session-<topic>-checkpoint-day<N>-<milestone>
```

## Quick reference: when you're tempted to hand-write

Ask yourself:

- **Is there an upstream commit that does this?** If yes, pick it. Always.
- **Is this a treewide-change adaptation?** `fixup:` with verbatim copy, list source hash.
- **Is this a signature-split artifact?** Same — verbatim fixup, list source hash.
- **Am I rewriting because "it's faster"?** Stop. That is the vendor-fork trap.
- **Has my fixup grown past 50 lines or 5 files?** Stop. You missed a prereq. Find it.

## Cross-platform notes

- `make -j$(nproc)`: macOS uses `$(sysctl -n hw.ncpu)`
- `git am --3way --fuzz=N` works on Windows git bash
- Use forward slashes in paths for cross-platform scripts

## Prompt template for the user

When invoking this skill, give the LLM:

```
Backport target:  [feature, e.g. "sched_ext scheduler class"]
Source upstream:  [version range, e.g. "v6.12 mainline"]
Target base:      [LTS tag/branch, e.g. "v6.6"]
Target configs:   [Kconfig symbols, e.g. "CONFIG_SCHED_CLASS_EXT=y"]
Known prereqs:    [list or "unknown — let build errors drive"]
Mode:             [strict upstream-only | exploratory]

Constraint: cherry-pick only. No hand-written code. Abort on semantic gap
and report before retrying.
```

## Further reading

- `references/case-study-sched-ext.md` — full worked example: 117 cherry-picks + 10 fixups, where each fixup came from, how conflict resolution played out across the BPF subsystem, what the failed first attempt looked like
- `references/conflict-playbook.md` — concrete recipes for the conflict patterns that recur in cross-version backports