# M5 review round 1 — fix exactly these points (same rules; only these files; only inside the current workspace)

Note: some files in this workspace also contain `performScrollTo()` test edits and two small fixes (MeScreen nickname
normalisation, FakeLocationViewModel locateFailed reset) that came from a separate, already-reviewed M4 fix. Leave those
hunks exactly as they are.

1. `app/src/test/java/edu/android/wut2eat/domain/BookingRulesTest.kt`: the test asserts
   `assertEquals(32, BOOKING_CODE_ALPHABET.length)` but the specified alphabet `"ABCDEFGHJKMNPQRSTUVWXYZ23456789"` has
   31 characters (the implementation is right). Expect 31 — or better, assert that every generated code character is
   contained in `BOOKING_CODE_ALPHABET` and that the alphabet has no ambiguous characters (I, L, O, 0, 1).
2. Files must end with exactly ONE newline and must not gain stray blank lines. Fix:
   - trailing extra blank line at the end of: `data/ShopLookup.kt`, `data/store/StoreCodec.kt`, `ui/detail/DetailPage.kt`,
     `ui/me/MeScreen.kt`, `ui/me/MeViewModel.kt`, `ui/multi/MultiplayerPage.kt`, `ui/nav/Routes.kt`, `ui/theme/Icons.kt`,
     `app/src/test/.../data/ShopLookupTest.kt`, `app/src/test/.../ui/me/MeViewModelTest.kt`;
   - the double blank line inside `ShopLookupTest.testPriorityWhenSourcesShareSameId`;
   - the two added double blank lines in `di/AppContainer.kt` (after `val shopLookup = …` and before `companion object`);
   - the added blank line after the imports in `ui/AppRoot.kt` (keep exactly one blank line between imports and KDoc).
3. `app/src/androidTest/java/edu/android/wut2eat/ui/booking/BookingScreenTest.kt` (and any booking-related assertions you
   added to `MeScreenTest.kt`): the booking form is long and the CI emulator screen is short — call `.performScrollTo()` on a
   node before `assertIsDisplayed()` / `performClick()` when it can be below the fold of the scrollable column (e.g. the
   party "+" button, `btn_confirm_booking`, the confirmation card's `btn_done`, the 我的 bookings section and its cancel button).
4. `app/src/main/java/edu/android/wut2eat/data/ShopLookup.kt`: make `bookings: BookingRepository` a required (non-null)
   constructor parameter — the container always provides it — and update the KDoc. Update every construction site
   (`AppContainer`, `ShopLookupTest`, any other test) to pass a repository (use `FakeBookingRepository` in tests).

Reply with the list of files you changed.
