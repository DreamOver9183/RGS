# M4 fix round 1 — crash on the 我的 tab (same rules: no git, no shell, only these files)

`connectedDebugAndroidTest`: 3 tests fail with
`ArrayIndexOutOfBoundsException: length=5; index=5 at …MeScreenKt…(MeScreen.kt:139)`.
`domain/Profile.kt` has `AVATAR_COUNT = 6`, but `AvatarColors` in `ui/theme/Theme.kt` defines only 5 colours, so the
sixth avatar circle (and `Avatar` with a saved index 5) crashes. Opening the 我的 tab crashes the real app.

1. `app/src/main/java/edu/android/wut2eat/ui/theme/Theme.kt`: make `AvatarColors` contain exactly `AVATAR_COUNT` (6)
   colours — add the missing one so the six are distinct and pleasant (spec suggestion: 0xFFE4572E, 0xFFD98A1C,
   0xFF2A7DE1, 0xFF3BA776, 0xFF8E5BD8, 0xFFE0607E).
2. New JVM test `app/src/test/java/edu/android/wut2eat/ui/theme/AvatarColorsTest.kt` (1 test):
   `assertEquals(AVATAR_COUNT, AvatarColors.size)` and all colours distinct.
3. Defensive indexing: in `ui/common/Avatar.kt` and `ui/me/MeScreen.kt`, read colours with
   `AvatarColors[index.coerceIn(0, AvatarColors.lastIndex)]` (or iterate `AvatarColors.indices` for the picker row) so a
   mismatch can never crash again.

Reply with the list of files you changed.
