# Review context for PR #5 (milestone M4: 我的 tab + fake location override)

- Specification: m4-spec.md (section 9 lists three minor findings deferred from the PR #3 review — double-tap
  navigation guard, test container hygiene, AppNavigationTest tab assertions — which this PR must resolve), plus
  m4-fix-1.md (the 我的 tab crashed because AvatarColors had 5 colours while AVATAR_COUNT is 6; fixed in a follow-up commit).
- The branch is based on the M3 tip that was already merged via PR #4, so pr5-diff.patch (against origin/main) is M4 only.
- Pay particular attention to: RouletteViewModel's fake-location handling (first emission only sets the label; later
  enable → move + pan; disable → re-locate or geo-failed; changes during a spin applied after it, including the
  error/empty paths), OverridableLocationSource (hasPermission() reads a StateFlow that may lag the DataStore flow by a
  moment), AppRoot's ifResumed/launchSingleTop guards, and the avatar index safety.
