# Case Study: sched_ext v6.12 → v6.6 backport

This document is the canonical worked example for the kernel-backport skill. Read it when you need concrete reference for what the methodology looks like in practice — what worked, what failed, and what the trade-offs felt like at each stage.

## Background

Goal: bring the `sched_ext` BPF-extensible scheduler class (introduced upstream in v6.12) to a v6.6 LTS base. Estimated initial scope: "drop in `kernel/sched/ext.c` and adapt a few APIs". Actual scope: 127 commits, touching 134 files, 21,915 lines of cumulative churn.

Final outcome: clean vmlinux link with `CONFIG_SCHED_CLASS_EXT=y` + `CONFIG_SCHED_CORE=y` + 29 related Kconfig options; scx_layered running on top.

## The failed first attempt (vendor-fork path)

The first attempt followed instinct: pull in the new files, fix build errors as they came up. After one week, vmlinux linked — but the tree had:

- 4 hand-written stub functions (typically `return 0;` with a comment)
- 5 sed-style API adaptations (changing call sites to match the older signature)
- 2 Makefile entries commented out to suppress incompatible subsystems
- 3 manual reverts of upstream cleanups (just edited the file, no `git revert`)
- 2 upstream function bodies copy-pasted directly into local files (no `git cherry-pick`, no commit record)

Nine files contained non-upstream code. The build worked. The kernel booted. But the result was structurally a vendor fork: no upstream patch could ever cleanly apply to those nine files again, and nobody could explain the semantic correctness of the adaptations without re-deriving them from scratch.

This attempt was discarded entirely. Tag `session5-stubs-hardened` preserves it as a cautionary anchor.

## The successful path

A rewrite from `v6.6` base, under the strict rule "only upstream commits, no hand-written code". Total result:

| Category | Count |
|---|---|
| Pure upstream cherry-picks | 117 |
| Controlled `fixup:` commits | 10 |
| Hand-written without upstream provenance | 0 |

Counterintuitively, this rewrite took **three days** — faster than the failed one-week vendor-fork attempt. The reason: every shortcut in the first attempt created two follow-on problems; cherry-picks accumulate cleanly.

## How the cherry-pick chain grew

The chain organized into roughly nine phases, each driven by build failures rather than upfront planning:

**Phase 1 — sched core refactors** (patches 1–16). Syscalls split, `wakeup_preempt` rename, deadline servers, sched_ext boilerplate + main commit `91bee1c5d756`. Found because the sched_ext main commit wouldn't apply without them.

**Phase 2 — sched/cpufreq prereqs** (patches 17–32). `dl_entity` init merge, `effective_cpu_util` refactor, `reweight_task`/`switching_to`/`check_class_changing` callbacks, cpufreq pressure feedback. Found via missing-symbol errors in phase 1.

**Phase 3 — BPF subsystem upgrade** (patches 33–56). `__bpf_kfunc_*` macros, open-coded iterators, `bpf_struct_ops_desc`, struct_ops dynamic registration, BPF token + LSM hooks, sleepable bit migration, register bounds sanitization. This phase was the dominant cost — sched_ext is built on top of BPF struct_ops, which needs the dynamic-registration infrastructure from `24118e70f777` and the CFI changes from `4f9087f16651` / `2cd3e3772e41`.

**Phase 4 — CFI + verifier finalization** (patches 57–63).

**Phase 5 — Manual fixups for BPF subsystem** (patches 64–65). Two `fixup:` commits closing API-split gaps. See "The 10 fixups" below.

**Phase 6 — sched_ext PR body** (patches 66–99). The 34 commits in the v6.12 sched_ext PR that sit between the boilerplate commit and the core-sched commit.

**Phase 7 — core-sched** (patch 100). `5b106d17a126`. Clean pick once phases 1–6 were in place.

**Phase 8 — cross-phase prereqs** (patches 101–102). Two upstream commits found via `Fixes:` annotations on sched_ext commits.

**Phase 9 — cross-phase fixups** (patches 103–104). Two more `fixup:` commits, one for a header include treewide change, one for the `reweight_task` signature transition.

## The 10 fixup commits in detail

Every fixup commit lists its source upstream commit hashes in the message. None contains new logic.

| Fixup hash | Lines | Source upstream | What it does |
|---|---|---|---|
| `25efe7068908` | +2/-1 | `6fe01d3cbb92` | Restore err/msk declarations dropped during a `-X ours` resolution |
| `8c327905e8e1` | +25/-112 | `902d67a2d40f` (PR tip) | `btf_struct_ops_tab`, `reg_set_min_max` body, `is_branch_taken` merge — pieces of BPF commits we couldn't cherry-pick cleanly because of cascade size |
| `ea8feddfdfa1` | +55/-9 | `894b6b1e9654`, `9df73f0667b8` | Forward decls in `bpf.h`, `btf_get_name` bridging, `bpf_global_percpu_ma` definition, five `arch_*_bpf_trampoline` weak helpers |
| `3eacd494c319` | +2/-1 | `fd92fceeb64f` (treewide), `3d7e10188ae0` | One `<linux/mmu_context.h>` include, one `__assign_str(x)` → `__assign_str(x, x)` adaptation. Both are treewide-change cases. |
| `595226a380fb` | +6/-5 | `902d67a2d40f` | `reweight_task` callback signature change for both `_scx` and `_fair` paths — signature-split case |
| `5f77afe444fb` | +7/-33 | (BPF verifier commits) | `check_cond_jmp_op` call site adaptations |
| `9e6383e19a73` | +125/-14 | (BPF verifier commits) | `__arg_trusted` decl_tag handling |
| `6d8f1534b6a4` | +9 | (BPF verifier commits) | Assign scalar id before spill |
| `e6d467651028` | +20 | (BPF verifier commits) | Mark trusted `PTR_TO_BTF_ID` known-zero — pattern lifted from the adjacent `PTR_TO_MEM` branch in the same function |
| `ee5266252b95` | +62/-3 | (BPF verifier commits) | `arg:trusted` in `btf_check_func_arg_match` |

Three categories explain why each fixup exists:

1. **Cascade cap.** Cherry-picking the full source commit would have dragged in a chain of 30+ more BPF commits not actually needed for the build. The fixup takes only the needed slice.
2. **Treewide changes.** A single upstream commit changes thousands of files (e.g., `fd92fceeb64f` changes every `__assign_str` call in the kernel). The fixup adapts just the one trace event sched_ext touches.
3. **API split.** Caller and implementation of a new signature live in different upstream commits, and the dependency graph forced one to be picked far ahead of the other.

## What the conflicts looked like in practice

Three patterns dominated:

**Pattern A: line drift in `#else` stub regions of `ext.h`.** Many sched_ext-era upstream commits each independently added the same `#define scx_enabled() false` stub in the `#ifdef`'s else branch. When cherry-picked into v6.6, these stubs collide with each other. Resolution: take only the stub the current commit *uniquely* needs (e.g., `scx_tick`, `scx_next_task_picked`), drop the redundant ones. Every kept line is from the upstream commit.

**Pattern B: forward declaration coexistence.** v6.6 base has `struct sched_param;`, upstream commit adds `struct sched_dl_entity;`. Resolution: keep both. Each line traceable.

**Pattern C: take-ours when HEAD already absorbed the change.** A prior cherry-pick already moved a function definition out of `core.c` into `syscalls.c`. The current commit's conflict in `core.c` is the deletion side; resolution: `-X ours` (= "keep the deletion already done"). No content is invented.

## Lessons that generalized

1. **Predicting the closure is hopeless.** Initial estimate was "20-30 prereq commits before sched_ext main can land". Actual: 117. The error wasn't quantitative — it was that the dominant cost (BPF struct_ops dynamic registration, CFI changes) wasn't visible from the surface of "we want a scheduler feature". Stop predicting; let build errors drive.

2. **`abort + find prereq + retry` is faster than "just resolve" a semantic conflict.** Hand-resolving a semantic conflict produces code that's neither upstream nor checked. The same conflict resolved twice — first incorrectly, then by picking the missing prereq — costs less time than debugging the incorrect resolution six commits later.

3. **Failed states have archival value.** Keeping `session5-stubs-hardened` as a tag (rather than deleting it) made it easy to point at the failed approach when temptation reappeared mid-project.

4. **Fixup size as a signal.** When a fixup was creeping past 50 lines, in every case there was an upstream commit we'd missed. Going back to find it was always cheaper than expanding the fixup.

5. **Cross-session continuity needs git, not memory.** This project spanned six days. CLAUDE.md's "Current progress" section + daily checkpoint tags meant each new session could verify the state in three commands (`git status -s`, `git log -1`, `git tag -l | tail`) and resume without re-deriving context.

## Anti-patterns observed in the failed attempt

For posterity, here are the specific shortcuts that produced the vendor-fork outcome — recognize them when an LLM proposes them:

- "I'll add a `WARN_ONCE` and `return 0` here so the build can proceed and we'll come back to it" — never came back; the warn became permanent.
- "The new API takes an extra parameter; I'll pass `NULL` for now" — wrong default for half the call sites, silent misbehavior at runtime.
- "Let me sed all callers of `bpf_xyz` to use the older name" — broke the ability to pick later fixes from upstream that touched those callers.
- "I'll comment out this Makefile entry to avoid the cascade" — the cascade was real and necessary; commenting it out meant the feature didn't actually work, only built.
- "Let me copy this function body from v6.12 into our file" — no commit record, no provenance, indistinguishable from invention.

Each of these felt locally rational. The aggregate was a tree that couldn't be re-synced with upstream.
