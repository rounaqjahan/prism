# Run tools: what Claude needs to run the app, and how you set it up

`lib/check-run-tools.py <platforms> --project <the session's working folder>` checks all of this when you choose "Claude runs it", before anything is built.

For each missing item the coordinator **asks first**: "<item> is missing. Want me to add it?"
- **MCPs**: on yes, Claude runs the `claude mcp add` command below itself. Then you do the one step only you can do: restart Claude Code and type `/prism`.
- **Everything else** (simulator, emulator, Xcode, login) needs you: the coordinator shows the exact steps below.

Afterwards it runs the check again. If you say no, that platform is reported unverified (R4).

| Platform | Drives the app with | Builds with | Device |
|---|---|---|---|
| ios (Mac only) | MCP `ios-simulator-mcp` (tap, type, describe, screenshot) | `xcodebuild` (Xcode must be closed) | the iOS simulator named by `run.ios_simulator` in `prism.json` |
| android | MCP `mobile` (`@mobilenext/mobile-mcp`) | the app's Gradle debug install | an Android emulator |

## Fixes

### ios-mcp
The iOS simulator MCP is missing, or is installed for one folder only. Claude can run this for you (it asks first):

    claude mcp add ios-simulator -s user -- npx -y ios-simulator-mcp

If an older one-folder copy exists (for example named `XcodeBuildMCP`), remove it first, from that folder: `claude mcp remove XcodeBuildMCP -s local`.

`-s user` makes it work from every folder. Restart Claude Code afterwards.

### mobile-mcp
The Android MCP is missing, or is installed for one folder only. Claude can run this for you (it asks first); remove a one-folder copy first with `claude mcp remove mobile -s local`:

    claude mcp add mobile -s user -e ANDROID_HOME="<your Android SDK folder>" -- npx -y @mobilenext/mobile-mcp@latest

The SDK folder is `$ANDROID_HOME` if set, else `~/Library/Android/sdk`.

Restart Claude Code afterwards.

### ios-simulator
**Needs you (Mac only).** The simulator named by `run.ios_simulator` in `prism.json` doesn't exist. Open Xcode → Settings → Components and install an iOS simulator runtime, then Window → Devices and Simulators → Simulators → + → that iPhone (or change `run.ios_simulator` to one you have: `xcrun simctl list devices available`). Close Xcode again before the run.

### xcode-open
**Needs you.** Xcode is open. Claude never runs `xcodebuild` while Xcode is open, so quit Xcode (⌘Q), then say "go".

### android-emulator
**Needs you.** No Android emulator. Open Android Studio → Device Manager → Create Virtual Device → pick a phone → download a system image → Finish. Claude boots it with `<Android SDK>/emulator/emulator -avd <name>`.

### adb
**Needs you.** `adb` isn't found. Install Android Studio's SDK Platform-Tools (Android Studio → Settings → Languages & Frameworks → Android SDK → SDK Tools → Android SDK Platform-Tools). Claude calls it by its full path, `<Android SDK>/platform-tools/adb`, so PATH doesn't matter.

### login
**Needs you.** No dev login. Create `~/.claude/prism/run-login.md` (outside the skill, never committed or shared) with the email, organization, environment and password Claude should log in with.
