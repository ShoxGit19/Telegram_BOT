"""Small git sync helper for bot-generated data files."""
import os
import shutil
import subprocess
import threading
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
DATA_PATHS = [
    "users.json",
    "feedbacks.csv",
    "translations.csv",
    "users.txt",
    "data/sent_flags.json",
]
_GIT_LOCK = threading.Lock()


def _find_git():
    git = shutil.which("git")
    if git:
        return git
    candidates = [
        Path.home() / "AppData/Local/Programs/Git/cmd/git.exe",
        Path.home() / "AppData/Local/Programs/Git/bin/git.exe",
        Path("C:/Program Files/Git/cmd/git.exe"),
        Path("C:/Program Files/Git/bin/git.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _run_git(git, args, timeout=60):
    return subprocess.run(
        [git, *args],
        cwd=REPO_DIR,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def auto_commit_push_data(message="Auto update bot data", paths=None):
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    git = _find_git()
    if not git:
        return False
    selected_paths = [
        path for path in (paths or DATA_PATHS)
        if (REPO_DIR / path).exists()
    ]
    if not selected_paths:
        return False
    with _GIT_LOCK:
        try:
            add = _run_git(git, ["add", "-f", *selected_paths])
            if add.returncode != 0:
                return False
            diff = _run_git(git, ["diff", "--cached", "--quiet", "--", *selected_paths])
            if diff.returncode == 0:
                return False
            commit = _run_git(git, ["commit", "-m", message, "--", *selected_paths])
            if commit.returncode != 0:
                return False
            push = _run_git(git, ["push", "origin", "main"], timeout=120)
            return push.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
