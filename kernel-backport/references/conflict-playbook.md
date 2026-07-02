# Conflict Resolution Playbook

Concrete recipes for the conflict patterns that recur in cross-major-version kernel backports. Read this when a cherry-pick conflicts and you're not sure which kind of conflict it is.

## Triage: line drift vs. semantic gap

The first decision when a conflict appears: is this a **line drift** conflict or a **semantic gap** conflict? They have different correct resolutions.

**Line drift** = the upstream hunk's code is fine, it just doesn't apply at the recorded line numbers because intervening commits moved things around.
- Symptom: the conflict markers show your `HEAD` side has roughly the same code structure as the upstream side, just shifted, renamed, or reordered.
- Resolution: place the upstream hunk in the right spot. Every line preserved comes from one side or the other; nothing is invented.

**Semantic gap** = upstream hunk references a symbol/field/macro/struct that genuinely doesn't exist in your tree yet.
- Symptom: the upstream side calls a function, uses a field, or includes a header that's not in your tree.
- Resolution: **abort the cherry-pick**, find the upstream commit that introduces the missing piece, pick it first, then retry.

Mistaking a semantic gap for line drift is the most common source of hidden vendor-fork drift. If you find yourself "adapting" the upstream hunk to use a different field name or a different function — stop. That's a semantic gap. Abort and find the prereq.

## Pattern: take-theirs when HEAD's content is stale

A previous cherry-pick already moved a chunk of code (e.g., split a function out of `core.c` into `syscalls.c`). The current commit conflicts in `core.c` because it expects to find the old location.

Resolution: `git checkout --theirs <file>` — accept the upstream side, which respects the new structure. Then verify by reading the file: the function shouldn't reappear in `core.c`.

This works when both sides are upstream; it's not "take theirs" in the sense of "ignore my changes", it's "the deletion was already done, so the upstream commit's view of the file (post-deletion) is correct".

## Pattern: take-ours when HEAD already absorbed the change

The mirror of the above. A previous cherry-pick already applied the change the current commit wants to make. The current commit conflicts because the change is already there.

Resolution: `git checkout --ours <file>`, then verify the desired change is present. If `git status` shows the file as still modified after, it's likely fine — the cherry-pick's delta on top of `ours` is empty.

## Pattern: forward declaration coexistence

Upstream adds `struct sched_dl_entity;` as a forward decl at the top of a header. Your tree has `struct sched_param;` (already there). The hunk conflicts because the upstream commit's context window includes the surrounding declarations.

Resolution: keep both forward decls. The merged file gets `struct sched_param;` and `struct sched_dl_entity;` side by side. Each line is traceable: the first to the v6.6 base, the second to the upstream commit.

This is mechanical, not semantic. Don't overthink it.

## Pattern: redundant `#else` stub regions

Upstream commits frequently add `#define foo() false` style stubs in the `#ifndef CONFIG_FOO` branch of a header. When you cherry-pick several such commits in sequence, each one independently tries to add similar stubs, and they collide.

Resolution: keep only the stub that the *current* commit uniquely introduces. Drop redundant `#define`s that are already present from prior cherry-picks. The kept stub is traceable to the current commit; the dropped ones are duplicates whose originals are traceable to earlier commits in the chain.

This pattern showed up extensively in sched_ext's `ext.h` — every sched_ext commit independently re-stubbed `scx_enabled()`, `scx_switched_all()`, etc.

## Pattern: signature transition split across commits

The new signature of a callback is introduced in commit A. The implementation that supplies the new signature is in commit B. Picking A without B means the build fails because the implementation doesn't match.

Two valid resolutions:

1. **Pick B first**, then A applies cleanly. Use `git log --all -S<new signature substring>` to find B.

2. If B is far down a chain you don't want to bring in yet, write a `fixup:` commit that **verbatim copies** the implementation from B into the right file. The fixup's commit message must list B's hash.

Do not "adapt" the implementation to "look like what B would have done". Either pick B, or verbatim-copy from B. Inference is forbidden.

## Pattern: treewide upstream change touching one file you care about

A single upstream commit changes a macro signature, header include style, or trace event format across thousands of files. You only need its effect on one or two files relevant to your backport.

Cherry-picking it would bring massive unrelated churn into your tree. Skipping it would leave your file using the old form.

Resolution: write a `fixup:` commit that applies the treewide change just to the files you need. Verbatim from the treewide upstream commit. Source hash in the commit message.

Examples from sched_ext: `fd92fceeb64f` (treewide `__assign_str` arity change) → fixed up one trace event. `3d7e10188ae0` (add `<linux/mmu_context.h>` include) → fixed up one `sched.h`.

## Pattern: `git am --3way` failures from `format-patch` exports

Sometimes you have a series exported as `.patch` files (e.g., from a previous backport effort) and `git am` fails with "patch does not apply".

Recipes:

- `git am --3way` — uses 3-way merge for hunks that don't apply cleanly. Often resolves line-drift conflicts automatically.
- `git am --3way --fuzz=N` — accept fuzzier context matching (N=2 or 3 is typical).
- `git am --abort` followed by `git apply --reject patch.file` — leaves `.rej` files showing what didn't apply. Useful for triage.

If `am --3way` produces a conflict, apply the same triage as for cherry-pick: line drift → resolve, semantic gap → abort + find prereq.

## When to abort

Abort the in-flight cherry-pick / am whenever:

- You've identified that the conflict is a semantic gap (missing prereq).
- The "resolution" you'd write involves inventing code or guessing at semantics.
- The conflict's scope has grown past what you can confidently reason about — better to back out, study the chain, and approach it fresh than to land a half-understood resolution.

`git cherry-pick --abort` is cheap. Bad resolutions are expensive.

## When NOT to abort

Don't abort just because:

- The conflict looks ugly. Mechanical line-drift conflicts often look bad but resolve cleanly.
- You'd rather "come back to it later". Conflict resolution doesn't get easier with time; the context you have right now (knowing exactly which commit you're picking and why) is the best you'll have.

## Diagnosis commands cheat sheet

```bash
# Where was a symbol introduced or last modified?
git log --all -S'<symbol>' --oneline | head

# What commits touched a specific file region?
git log --all -L<start>,<end>:<file>

# What does the upstream commit look like for a file?
git show <hash> -- <file>

# What's the state of the in-flight cherry-pick?
cat .git/CHERRY_PICK_HEAD     # commit being picked
git diff --cc                  # combined conflict view

# After resolving, validate before continuing:
git diff --staged              # what's about to be committed
git cherry-pick --continue

# Backtrack a too-aggressive resolution:
git cherry-pick --abort
```

## Anti-recipes (do not do these)

- **Don't `git checkout HEAD <file>` to drop the conflict.** That silently throws away the commit's changes; the resulting "completed" cherry-pick has no effect, but it'll look applied. Future cherry-picks that depend on it will fail mysteriously.
- **Don't manually edit the conflict markers away by retyping code from memory.** If you can't trace each retained line to one side of the conflict, it's invention.
- **Don't squash an "in progress" cherry-pick into a `fixup:` commit to make the conflict go away.** Fixup commits exist for specific cases (see SKILL.md); they are not a "skip this commit" mechanism.
