## Summary
- Adopt Android Gradle Plugin 9.3.0 (supports compileSdk 37, Build Tools 36.0.0)
- Ignore the root `.kotlin/` directory
- CI: add `assembleRelease` (R8) to the build job, a parallel emulator job running `connectedDebugAndroidTest` (API 35 Google APIs), and per-PR concurrency
- Docs: AGENTS.md and README.md updated for the toolchain and CI

First milestone (M0) of the multi-screen feature work.

## Test plan
- [x] Local: `help assembleDebug assembleRelease` succeed with AGP 9.3.0
- [ ] CI `build` job green
- [ ] CI `instrumented` job green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
