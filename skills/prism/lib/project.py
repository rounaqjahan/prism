#!/usr/bin/env python3
"""The one place Prism learns about a project.

Everything project-specific (repos, base branches, gates, file rules, feature flags,
the shared layer) lives in <workspace>/.prism/prism.json. Paths in it are relative
to the workspace folder (the folder that holds .prism/) unless absolute.

Which project: $PRISM_PROJECT, then the active run's "project", then a .prism/
folder above the current directory, then the last project set by `project.py use`.
"""
import json
import os
import platform as _platform
import shlex
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PACKS = SKILL_DIR / "platforms"
CONFIG_NAME = "prism.json"
SHARED = "engine"
OS = {"Darwin": "mac", "Windows": "windows"}.get(_platform.system(), "linux")


class NoProject(SystemExit):
    pass


def prism_home():
    return Path(os.environ.get("FG_HOME", Path.home() / ".claude" / "prism"))


def norm(path):
    return str(path).replace("\\", "/") if path is not None else path


def under(path, root):
    path, root = norm(path), norm(root).rstrip("/")
    if OS == "windows":
        path, root = path.lower(), root.lower()
    return path == root or path.startswith(root + "/")


def _as_config(path):
    path = Path(path).expanduser()
    if path.is_dir():
        path = path / ".prism" / CONFIG_NAME if (path / ".prism").is_dir() else path / CONFIG_NAME
    return path if path.is_file() else None


def _from_active_run():
    pointer = prism_home() / "active"
    if not pointer.exists():
        return None
    run = prism_home() / "runs" / pointer.read_text().strip() / "run.json"
    try:
        return json.loads(run.read_text()).get("project")
    except (OSError, ValueError):
        return None


def config_path(required=True):
    candidates = [os.environ.get("PRISM_PROJECT"), _from_active_run()]
    here = Path.cwd()
    candidates += [str(folder) for folder in [here, *here.parents] if (folder / ".prism" / CONFIG_NAME).is_file()][:1]
    pointer = prism_home() / "project"
    if pointer.exists():
        candidates.append(pointer.read_text().strip())
    for candidate in candidates:
        if candidate and _as_config(candidate):
            return _as_config(candidate).resolve()
    if required:
        raise NoProject("Prism has no project yet. Run `/prism setup` first "
                        "(or set PRISM_PROJECT to a folder that has .prism/prism.json).")
    return None


def prism_dir():
    return config_path().parent


def workspace():
    folder = prism_dir()
    return folder.parent if folder.name == ".prism" else folder


_CACHE = {}


def config():
    path = config_path()
    key = (str(path), path.stat().st_mtime)
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[key]


def pack(name):
    file = PACKS / f"{name}.json"
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else {"name": name}


def known_packs():
    return sorted(p.stem for p in PACKS.glob("*.json"))


def resolve(path):
    if path is None:
        return None
    p = Path(os.path.expandvars(str(path))).expanduser()
    return norm(p if p.is_absolute() else (workspace() / p).resolve())


def _rule_doc(doc_, repo_path):
    """A rule doc is relative to its repo; if it isn't there, relative to the workspace."""
    p = Path(os.path.expandvars(str(doc_))).expanduser()
    if p.is_absolute():
        return norm(p)
    in_repo = Path(repo_path) / p
    return norm(in_repo) if in_repo.exists() else resolve(doc_)


def doc_path(doc_):
    """A doc named in file_rules / max_file_lines: absolute, workspace-relative or .prism-relative."""
    if not doc_:
        return None
    for candidate in (resolve(doc_), norm(prism_dir() / doc_)):
        if Path(candidate).exists():
            return candidate
    return resolve(doc_)


def _repo(entry, platform):
    repo = dict(entry)
    repo["path"] = resolve(entry["path"])
    repo["git_root"] = resolve(entry.get("git_root") or entry["path"])
    repo.setdefault("role", "app")
    repo.setdefault("base", "main")
    repo.setdefault("source", ["."])
    repo["rules"] = [_rule_doc(r, repo["path"]) for r in entry.get("rules", [])]
    repo["platform"] = platform
    return repo


def platforms():
    return list(config().get("platforms", {}))


def shared():
    data = config().get("shared")
    return data if data and data.get("repos") else None


def shared_users():
    data = shared()
    return list(data.get("used_by", [])) if data else []


def repos():
    table = {p: [_repo(r, p) for r in spec.get("repos", [])] for p, spec in config().get("platforms", {}).items()}
    if shared():
        table[SHARED] = [_repo(dict(r, role=r.get("role", "engine")), SHARED) for r in shared()["repos"]]
    return table


def all_roots():
    return [r["path"] for rs in repos().values() for r in rs]


def names():
    try:
        table = {p: config()["platforms"][p].get("name") or pack(p).get("name", p) for p in platforms()}
        if shared():
            table[SHARED] = shared().get("name", "Shared layer")
        return table
    except NoProject:
        return {p: pack(p).get("name", p) for p in known_packs()}


def name_of(platform):
    return pack(platform).get("name", platform)


def name(platform):
    return names().get(platform, platform)


def kinds():
    try:
        return list(dict.fromkeys((config().get("kinds") or ["feature"]) + ["bootstrap"]))
    except NoProject:
        return ["feature", "bootstrap"]


def feature_flags():
    return config().get("feature_flags") or None


def run_settings():
    defaults = {"ios_simulator": "iPhone 16", "screenshots": "~/Desktop/{feature} screenshots"}
    return defaults | (config().get("run") or {})


def screenshots_folder(feature_title):
    return norm(Path(run_settings()["screenshots"].replace("{feature}", feature_title)).expanduser())


def doc(name_):
    return norm(prism_dir() / name_)


def guardrails():
    return config().get("guardrails", [])


def _gradlew(cwd):
    return str(Path(cwd) / "gradlew.bat") if OS == "windows" else "./gradlew"


def _expand(token, repo):
    token = token.replace("{sim}", run_settings()["ios_simulator"])
    if token == "{gradlew}":
        return _gradlew(repo["path"])
    return token


def _argv(cmd, repo):
    argv = shlex.split(cmd, posix=OS != "windows") if isinstance(cmd, str) else list(cmd)
    argv = [_expand(t, repo) for t in argv]
    if argv and argv[0] in ("sh", "bash") and OS == "windows":
        bash = shutil.which("bash")
        argv[0] = bash or argv[0]
    elif argv:
        found = shutil.which(argv[0], path=os.environ.get("PATH")) if not os.path.isabs(argv[0]) and "/" not in argv[0] else None
        if found and OS == "windows":
            argv[0] = found
    return argv


def package_manager(folder):
    folder = Path(folder)
    for parent in [folder, *folder.parents][:4]:
        for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun"),
                         ("package-lock.json", "npm")):
            if (parent / lock).exists():
                return pm
    return "npm"


FROZEN = {"pnpm": "--frozen-lockfile", "yarn": "--frozen-lockfile", "npm": "ci", "bun": "--frozen-lockfile"}


def xcode_scheme(folder):
    folder = Path(folder)
    for pattern in ("*.xcworkspace", "*.xcodeproj"):
        found = sorted(p for p in folder.glob(pattern) if p.name != "project.xcworkspace")
        if found:
            return found[0].stem, ("-workspace" if pattern == "*.xcworkspace" else "-project"), found[0].name
    if (folder / "Package.swift").exists():
        import re
        match = re.search(r'name:\s*"([^"]+)"', (folder / "Package.swift").read_text(errors="ignore"))
        return (match.group(1) if match else folder.name), None, None
    return None, None, None


def materialize_gate(platform, role, folder):
    """Turn a platform pack's default gate into concrete commands for one repo folder."""
    folder = Path(folder)
    scripts = {}
    if (folder / "package.json").exists():
        try:
            scripts = json.loads((folder / "package.json").read_text(encoding="utf-8")).get("scripts", {})
        except ValueError:
            scripts = {}
    pm = package_manager(folder)
    scheme, flag, container = xcode_scheme(folder) if platform == "ios" else (None, None, None)
    out = []
    for entry in pack(platform).get("gate", {}).get(role, pack(platform).get("gate", {}).get("app", [])):
        entry = dict(entry)
        if entry.get("if_script") and entry.pop("if_script") not in scripts:
            continue
        cmd = []
        for token in entry["cmd"]:
            if token == "{pm}":
                cmd.append(pm)
            elif token == "{frozen}":
                locked = any((p / lock).exists() for p in [folder, *folder.parents][:4]
                             for lock in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock"))
                if locked:
                    cmd = (cmd[:-1] + ["ci"]) if pm == "npm" else cmd + [FROZEN[pm]]
            elif token == "{scheme}":
                if not scheme:
                    cmd = None
                    break
                cmd.append(scheme)
            else:
                cmd.append(token)
        if cmd is None:
            continue
        if platform == "ios" and flag and "-scheme" in cmd and flag not in cmd:
            i = cmd.index("-scheme")
            cmd[i:i] = [flag, container]
        entry["cmd"] = cmd
        out.append(entry)
    return out


def gate_commands(platform, repo):
    """[{'argv': [...], 'cmd': 'display string', 'build': bool, 'needs_mac': bool}]"""
    entries = repo.get("gate")
    if entries is None:
        entries = materialize_gate(platform, repo.get("role", "app"), repo["path"])
    out = []
    for entry in entries:
        entry = entry if isinstance(entry, dict) else {"cmd": entry}
        if entry.get("os") and OS not in entry["os"]:
            continue
        argv = _argv(entry["cmd"], repo)
        out.append({"argv": argv, "cmd": " ".join(entry["cmd"]) if isinstance(entry["cmd"], list) else entry["cmd"],
                    "build": bool(entry.get("build")), "needs_mac": bool(entry.get("needs_mac"))})
    return out


def needs_mac(platform):
    return bool(pack(platform).get("needs_mac"))


def java_home():
    if os.environ.get("JAVA_HOME"):
        return os.environ["JAVA_HOME"]
    candidates = {
        "mac": ["/Applications/Android Studio.app/Contents/jbr/Contents/Home"],
        "windows": [r"C:\Program Files\Android\Android Studio\jbr"],
        "linux": ["/opt/android-studio/jbr", str(Path.home() / "android-studio/jbr")],
    }[OS]
    return next((c for c in candidates if Path(c).exists()), None)


def android_sdk():
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(key):
            return Path(os.environ[key])
    return {"mac": Path.home() / "Library/Android/sdk",
            "windows": Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Android/Sdk",
            "linux": Path.home() / "Android/Sdk"}[OS]


def file_rules(platform):
    return [r for r in config().get("file_rules", []) if r.get("platform") in (platform, "*")]


def max_lines(platform):
    rules = config().get("max_file_lines", {})
    return rules.get(platform, rules.get("*"))


def standing_rules():
    base = []
    for name_ in known_packs():
        for rule in pack(name_).get("standing_rules", []):
            base.append(dict(rule, platforms=rule.get("platforms", [name_])))
    try:
        base += config().get("standing_rules", [])
    except NoProject:
        pass
    return base


def source_exts():
    exts = set()
    for name_ in known_packs():
        exts |= set(pack(name_).get("exts", []))
    return exts


def use(path):
    found = _as_config(path)
    if not found:
        raise SystemExit(f"no {CONFIG_NAME} in {path} (or its .prism/ folder)")
    prism_home().mkdir(parents=True, exist_ok=True)
    (prism_home() / "project").write_text(norm(found.resolve()) + "\n")
    return found


def main():
    args = sys.argv[1:]
    if not args or args[0] == "where":
        print(norm(config_path()))
    elif args[0] == "use" and len(args) > 1:
        print(f"Prism project: {norm(use(args[1]))}")
    elif args[0] == "show":
        print(json.dumps({"config": norm(config_path()), "workspace": norm(workspace()), "os": OS,
                          "platforms": names(), "repos": repos(), "kinds": kinds(),
                          "feature_flags": feature_flags()}, indent=2))
    else:
        raise SystemExit("usage: project.py [where | use <folder> | show]")


if __name__ == "__main__":
    main()
