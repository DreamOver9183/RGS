# Review context for PR #6 (milestone M5: demo booking flow + bookings list on the 我的 tab)

- Specification: m5-spec.md, plus m5-fix-1.md (review round 1: booking-code alphabet test, trailing newlines,
  `performScrollTo()` in booking UI tests, `ShopLookup.bookings` made non-null).
- PR #5 (M4) is already merged into main, so pr6-diff.patch (against origin/main) is M5 only.
- Verified locally by the author: 103 JVM tests, lintDebug (0 errors), assembleDebug/Release, and 19 instrumented
  tests on both a normal and a 720x1280 / 320dpi emulator display.
- Pay particular attention to: `bookingSlots` (closed weekday, 30-minute steps, last slot 60 minutes before closing,
  today's past slots dropped, overnight/edge opening hours from `fakeExtras`), `validateBooking` order, the booking
  codec (ISO date / `HH:mm`, dropping unparsable entries, JSON compatibility with older values), `BookingViewModel`
  (injected `Clock`, preselection, keeping the time when switching dates, double-submit guard, no side effects inside
  `update {}`), `BookingRepository.cancel`, `ShopLookup` order (registry → favorites → bookings → seed), the 我的 tab's
  cancel confirmation, and the navigation guards for `BookingRoute`.
