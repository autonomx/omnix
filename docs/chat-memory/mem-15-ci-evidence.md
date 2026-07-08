# MEM-15 exact-head CI evidence

The MEM-15 implementation branch is based on merged MEM-14 commit `69c3a321d63ee38f8208f82c229a7a3dd7bddee8` and is not complete until both required pull-request workflows succeed on the exact final branch head:

- RPG Phase 0 architecture compliance
- RPG deterministic PR gates

Any failing check must be corrected on `tmp-mem15-gate`; the resulting new head must pass both checks before squash merge into `rpg`.
