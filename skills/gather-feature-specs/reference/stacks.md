# Stack detection and design guidance

Check these files at the repo root, then one level down (monorepos). The first strong match wins; if several match, ask which one the plan is for.

| Signal | Stack | Confirm by | UI framework | Usual test framework |
|---|---|---|---|---|
| `Package.swift`, `*.xcodeproj`, `*.xcworkspace` | Swift / iOS | `import SwiftUI` or `import UIKit` in sources | SwiftUI or UIKit | XCTest / Swift Testing |
| `build.gradle(.kts)` with `com.android.*` plugin | Kotlin / Android | `androidx.compose` dependency, `@Composable` | Jetpack Compose or Views | JUnit, Robolectric, Compose UI tests |
| `pubspec.yaml` with `flutter:` | Dart / Flutter | `package:flutter/` imports | Flutter (Material / Cupertino) | `flutter_test` |
| `package.json` with `react-native` or `expo` | TypeScript / React Native | `app.json`, `metro.config.js`, `*.native.tsx` | React Native | Jest |
| `package.json` with `react` and `vite` / `next` / `react-scripts` | TypeScript / React web | `index.html`, `vite.config.*`, `next.config.*` | React DOM | Vitest / Jest / Playwright |
| `package.json` workspaces, `pnpm-workspace.yaml`, `turbo.json`, `nx.json` | JS/TS monorepo | `packages/*`, `apps/*` | per package | per package |
| `build.gradle(.kts)` without Android plugin, `pom.xml` | Kotlin / Java (JVM) | — | — | JUnit |
| `go.mod`, `Cargo.toml`, `pyproject.toml`, `Gemfile` | Go / Rust / Python / Ruby | — | usually none (backend) | language default |

## Architecture: where to look
Read these first; they override any general assumption:
- `ARCHITECTURE.md` (any depth), `docs/architecture*`, ADRs (`docs/adr/`, `docs/decisions/`)
- `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `CODING_STANDARDS.md`
- leaf `CLAUDE.md` files next to the module the feature touches

Then confirm from code:
- **Screens:** `Views/`, `screens/`, `presentation/`, `features/<x>/`, `app/`, `pages/`
- **Logic:** `ViewModel(s)/`, `view_models/`, `viewmodel/`, `hooks/`, `store/`, `slices/`, `bloc/`, `cubit/`
- **Data:** `Repositories/`, `repository/`, `network/`, `api/`, `services/`, RTK Query `*Api.ts`
- **Navigation:** coordinators, `NavHost`, `GoRouter`, `react-navigation` stacks, route constants
- **DI:** init/constructor injection, Hilt/Koin, Provider/Riverpod/get_it, React context providers
- **Strings:** `Localizable.strings` / `.xcstrings`, `res/values*/strings.xml`, `l10n/*.arb`, `locales/*.json`, i18n libraries

## Design guidance by stack
Cite the specific page used, not just the site.

| Stack | Guidance |
|---|---|
| Swift / iOS | Apple Human Interface Guidelines: https://developer.apple.com/design/human-interface-guidelines |
| Kotlin / Android | Material Design 3: https://m3.material.io · Android developer guides: https://developer.android.com/design |
| Flutter | Material 3 (as above) for Material widgets; Apple HIG for Cupertino widgets; Flutter docs: https://docs.flutter.dev/ui |
| React web | WAI-ARIA Authoring Practices: https://www.w3.org/WAI/ARIA/apg/ · MDN: https://developer.mozilla.org |
| React Native | Apple HIG for the iOS side, Material 3 for the Android side; React Native docs: https://reactnative.dev/docs |

Accessibility for every stack: WCAG 2.2 (https://www.w3.org/TR/WCAG22/) plus the platform's own accessibility guide.
