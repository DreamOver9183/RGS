# Milestone M0 spec: CI expansion + git ignore

Read `gemini-rules.md` (same folder as this spec) first and follow it.

Files you may modify: `.github/workflows/android-ci.yml` and `.gitignore`. Nothing else.

## 1. `.gitignore`
Add a line `.kotlin/` (Kotlin compiler/daemon session data) in the build-output group. Keep everything else.

## 2. `.github/workflows/android-ci.yml`
Rewrite it as below. Keep the existing name, triggers (`pull_request`, `push` to `main`, `workflow_dispatch`),
`permissions: contents: read`, and the exact action versions already used in the file
(`actions/checkout@v7`, `actions/setup-java@v6` temurin 25, `gradle/actions/setup-gradle@v6` with
`cache-provider: basic` and `add-job-summary: always`, `android-actions/setup-android@v4.0.4`,
`actions/upload-artifact@v7`).

### Workflow-level concurrency
```yaml
concurrency:
  group: ci-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

### Job `build` (existing job, modified)
- `timeout-minutes: 30`.
- Same setup steps as today (checkout, JDK 25, Gradle, Android SDK, `sdkmanager "platforms;android-37.0" "build-tools;36.0.0"`).
- Gradle step name: "Run unit tests, lint, and assemble debug and release APKs";
  command: `./gradlew testDebugUnitTest lintDebug assembleDebug assembleRelease --stacktrace --no-daemon`.
- Keep the two existing upload steps (reports always; debug APK on success).
- Add an upload step on failure only (`if: ${{ failure() }}`), artifact name `r8-mapping`, path
  `app/build/outputs/mapping/release/`, `if-no-files-found: ignore`, `retention-days: 14`.

### Job `instrumented` (new, runs in parallel with `build`)
- `name: Compose UI tests (emulator)`, `runs-on: ubuntu-latest`, `timeout-minutes: 45`.
- Steps, in order:
  1. Checkout, JDK 25, Gradle, Android SDK, and the same `sdkmanager` step as `build`.
  2. Enable KVM:
     ```yaml
     - name: Enable KVM
       run: |
         echo 'KERNEL=="kvm", GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"' | sudo tee /etc/udev/rules.d/99-kvm4all.rules
         sudo udevadm control --reload-rules
         sudo udevadm trigger --name-match=kvm
     ```
  3. AVD cache (`id: avd-cache`) with `actions/cache@v6`, paths `~/.android/avd/*` and `~/.android/adb*`,
     key `avd-35-google_apis-x86_64-v1`.
  4. "Create AVD and generate snapshot for caching", only `if: steps.avd-cache.outputs.cache-hit != 'true'`,
     using `reactivecircus/android-emulator-runner@v2.38.0` with:
     `api-level: 35`, `target: google_apis`, `arch: x86_64`, `cores: 4`, `force-avd-creation: false`,
     `emulator-options: -no-window -gpu swiftshader_indirect -noaudio -no-boot-anim -camera-back none`,
     `disable-animations: false`, `script: echo "Generated AVD snapshot for caching."`.
  5. "Run connected Android tests" using the same action and the same inputs except:
     `emulator-options: -no-snapshot-save -no-window -gpu swiftshader_indirect -noaudio -no-boot-anim -camera-back none`,
     `disable-animations: true`, `emulator-boot-timeout: 900`,
     `script: ./gradlew connectedDebugAndroidTest --stacktrace --no-daemon`.
  6. Upload step `if: ${{ always() }}`, artifact name `android-test-reports`, paths
     `app/build/outputs/androidTest-results/**` and `app/build/reports/androidTests/**`,
     `if-no-files-found: warn`, `retention-days: 14`.
- No secrets. No Maps API key.

Use 2-space YAML indentation consistent with the existing file, and keep step names descriptive in English.
