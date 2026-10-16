## Summary

- **收藏抽籤**: the 收藏 tab header gets a 從收藏抽 button that opens a new sub-page (`FavoritesDrawRoute`). It spins a reel over the favorites only (no open-now or radius filter) and links the result to its detail page.
- **多人抽**: the 多人 tab is no longer a placeholder. Four player cards each have their own reel and button and may be pressed at the same time. The pool is 附近 (Places, for Home's current area) or 收藏 (favorites only, works without Places). 決勝 is enabled once all four have results and picks one of them; 重來 clears the round.
- **One Places search per area**: `NearbyPoolCache` (in `Session.nearby`) caches the 附近 pool per area behind a `Mutex`, so four simultaneous presses share one fetch. Empty results are not cached.
- **Pure pool draw**: `domain/Pool.kt` adds `drawFromPool` and `pickIndex`.
- **Shared UI pieces**: `ui/common/ReelGate` lets a ViewModel wait for a reel animation, with a timeout. `ReducedMotion` is extracted from `Panel` and reused by the new screens. The favorites-draw ViewModel ignores a second tap during a draw, and the multiplayer ViewModel ignores a second tap on a slot that is still spinning.
- **Draw stats**: `StatsRepository` stores `draw_count` (int) in the single DataStore. `AppContainer.recordDraw` registers each drawn shop and counts it once per completed reel (Home, favorites draw, each multiplayer player); 決勝 does not count.
- **Docs**: AGENTS.md and README.md describe the new structure, flows, persistence key, Places cost note, and test coverage.

This branch also merges M2's review fix (PR #3, `fix(favorites): resolve detail shop once and reserve result-row height`). That commit will drop out of this diff once #3 is merged into `main`.

## Test plan

- [x] `testDebugUnitTest`: 74 tests in 22 classes, all passing (72 from M3 + 2 from the M2 fix)
- [x] `lintDebug`: 0 errors, 9 warnings (only the known IDs: AndroidGradlePluginVersion, GradleDependency, NewerVersionAvailable ×3, OldTargetApi, DataExtractionRules, DiscouragedApi, LockedOrientationActivity)
- [x] `assembleDebug` and `assembleRelease` (R8) succeed
- [x] `connectedDebugAndroidTest` on an API 37 emulator: 13 tests in 7 classes, all passing (new: `FavoritesDrawScreenTest` ×1, `MultiplayerScreenTest` ×2; `AppNavigationTest` now asserts real tab content)
- [x] Manual smoke test on the emulator: 收藏 shows 從收藏抽; the favorites draw yields a result; 多人 with the 收藏 pool gives four independent results from back-to-back presses; 決勝 shows the winner card; no app crashes
- [ ] Antigravity Gemini review

🤖 Generated with [Claude Code](https://claude.com/claude-code)
