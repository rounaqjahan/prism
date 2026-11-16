import json
import os
from contextlib import contextmanager
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def home():
    return Path(os.environ.get("FG_HOME", Path.home() / ".claude" / "prism"))


def runs_dir():
    return home() / "runs"


def run_dir(slug):
    return runs_dir() / slug


def active_slug():
    pointer = home() / "active"
    if not pointer.exists():
        return None
    slug = pointer.read_text().strip()
    return slug if slug and (run_dir(slug) / "run.json").exists() else None


def branch_slug(slug=None):
    slug = slug or active_slug()
    path = run_dir(slug) / "run.json" if slug else None
    if path and path.exists():
        return json.loads(path.read_text()).get("parent") or slug
    return slug


def set_active(slug):
    home().mkdir(parents=True, exist_ok=True)
    pointer = home() / "active"
    if slug:
        pointer.write_text(slug + "\n")
    elif pointer.exists():
        pointer.unlink()


def load_graph():
    graph = json.loads((SKILL_DIR / "graph.json").read_text())
    import project
    graph["platforms"] = project.platforms()
    users = project.shared_users()
    for node in graph["nodes"]:
        node["after"] = [dict(a, only=users) if isinstance(a, dict) and a.get("only") == "@shared" else a
                         for a in node.get("after", [])]
    return graph


def _lock(handle):
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX)


def _unlock(handle):
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_UN)


def read_run(slug):
    return json.loads((run_dir(slug) / "run.json").read_text())


def write_run(slug, run):
    path = run_dir(slug) / "run.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(run, indent=2) + "\n")
    os.replace(tmp, path)
    import progress
    progress.write(slug, run)


@contextmanager
def locked_run(slug):
    lock_path = run_dir(slug) / ".lock"
    with open(lock_path, "w") as lock:
        _lock(lock)
        try:
            run = read_run(slug)
            yield run
            write_run(slug, run)
        finally:
            _unlock(lock)
