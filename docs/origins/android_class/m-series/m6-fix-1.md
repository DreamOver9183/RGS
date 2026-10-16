# M6 review round 1 — fix exactly these points (same rules in gemini-rules.md; only these files; only inside the current workspace)

1. **The JVM tests do not compile.** `ShopLookup` now takes `(registry, favorites, customShops, bookings)`, but these
   positional call sites still pass three arguments:
   - `app/src/test/java/edu/android/wut2eat/ui/booking/BookingViewModelTest.kt` lines ~67, ~103, ~133:
     `ShopLookup(registry, favorites, bookings)`
   - `app/src/test/java/edu/android/wut2eat/ui/detail/DetailViewModelTest.kt` lines ~49, ~84, ~103, ~146:
     `ShopLookup(registry, favorites, FakeBookingRepository())`
   Pass `FakeCustomShopRepository()` as the third argument (use named arguments if clearer). Re-check every
   `ShopLookup(` in `app/src/test` and `app/src/androidTest`.

2. `ui/common/LocationPicker.kt` — the touch detector is wrong: the map is an `AndroidView` that consumes the pointer
   changes, so `waitForUpOrCancellation()` returns (as "cancelled") on the first consumed move and `onMapTouch(false)`
   fires while the finger is still dragging the map. Replace the detector body with an Initial-pass loop that ignores
   consumption and always resets:
   ```kotlin
   .pointerInput(Unit) {
       awaitEachGesture {
           awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
           onMapTouch(true)
           try {
               do {
                   val event = awaitPointerEvent(PointerEventPass.Initial)
               } while (event.changes.any { it.pressed })
           } finally {
               onMapTouch(false)
           }
       }
   }
   ```
   (import `androidx.compose.ui.input.pointer.PointerEventPass`; drop the unused `waitForUpOrCancellation` import).
   Also use `rememberUpdatedState(onMapTouch)` inside `LocationPicker` and call the updated value from the
   `pointerInput(Unit)` block, so a new lambda is not ignored.

3. `ui/addshop/AddShopViewModel.kt` — each setter clears only its own errors (pure `copy` inside `update`):
   `setName` removes `NameRequired` and `NameTooLong`; `setType` removes `TypeRequired`; `setNote` removes
   `NoteTooLong` and caps the input with `take(MAX_SHOP_NOTE + 10)` (like the name).
   Add to `app/src/test/java/edu/android/wut2eat/ui/addshop/AddShopViewModelTest.kt` (2 new tests):
   - double tap: with a valid form, call `save()` twice before `runCurrent()` → exactly one shop in the repository and
     `newId` invoked exactly once (count the calls in the lambda);
   - after a `save()` with a blank name and blank type, `setType("小吃店")` removes `TypeRequired` but keeps `NameRequired`.

4. `ui/multi/MultiplayerScreen.kt` winner card: with three `TextButton`s (預訂, 分享, 詳情) beside the name, the name
   column gets only ~120dp on a 360dp-wide phone. Put the name/info `Column` on top (full width) and the three buttons in
   a `Row` below it, aligned to the end (`Arrangement.spacedBy(4.dp, Alignment.End)`), inside the same card.
   Keep every existing text, callback, and the card styling. Make sure `MultiplayerScreenTest` still finds the
   winner text and buttons (do not rename anything).

5. `ui/share/ShareScreen.kt`:
   - The rating text is a hardcoded format string (`"★ %.1f"`). Add `<string name="share_rating">★ %1$.1f</string>` and
     use `stringResource(R.string.share_rating, extras.rating)`; remove the `Locale` import if unused.
   - When `shop.type` is blank the template yields `店名（）`. Add
     `<string name="share_template_no_type">%1$s 推薦你一間餐廳：\n%2$s\n%3$s\n%4$s</string>` (sender, name, note, url) and
     use it when `shop.type.isBlank()`.

6. `app/src/androidTest/java/edu/android/wut2eat/ui/share/ShareScreenTest.kt`: remove the "unnecessary non-null
   assertion" warning (e.g. `val text = checkNotNull(sharedText)` and assert on `text`).

7. Stray double blank lines: remove the extra blank line in `ui/me/MeScreen.kt` (around line 371–372, two consecutive
   blank lines) and in `app/src/main/res/values/strings.xml` (lines ~33–34, after `tab_me`). Exactly one blank line
   remains in each place. Files end with exactly one newline.

Reply with the list of files you changed.
