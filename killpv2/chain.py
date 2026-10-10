"""Run chaining: when this GitHub Actions run approaches its end, dispatch the next run via GH_PAT.

Triggered from inside the Python process (so it also works if the workflow's last step is skipped),
guarded by a marker file so the workflow step and this module never double-trigger.
Only the OWNER is notified.
"""
import os
import json
import time
import urllib.request
import urllib.error

from . import settings

MARKER = os.path.join(settings.ROOT_DIR, ".next_run_triggered")


def already_triggered():
    return os.path.exists(MARKER)


def trigger_next_run(log=None, ref="main"):
    log = log or (lambda *a, **k: None)
    if not settings.GH_PAT or not settings.REPO_FULL_NAME:
        return False, "GH_PAT or GITHUB_REPOSITORY missing"
    if already_triggered():
        return True, "already triggered"
    url = f"https://api.github.com/repos/{settings.REPO_FULL_NAME}/actions/workflows/{settings.WORKFLOW_FILE}/dispatches"
    req = urllib.request.Request(url, data=json.dumps({"ref": ref}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {settings.GH_PAT}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "kill_pv2"})
    last = ""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status in (204, 200):
                    with open(MARKER, "w") as f:
                        f.write(str(int(time.time())))
                    log("system", "next workflow run dispatched")
                    return True, "dispatched"
                last = f"HTTP {r.status}"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}"
            if e.code in (401, 403, 404):
                break
        except Exception as e:
            last = str(e)
        time.sleep(3 * (attempt + 1))
    log("system", f"next run dispatch failed: {last}", "error")
    return False, last


def runs_remaining_in_queue():
    """How many runs are queued/in progress (to avoid piling up)."""
    if not settings.GH_PAT or not settings.REPO_FULL_NAME:
        return None
    try:
        url = f"https://api.github.com/repos/{settings.REPO_FULL_NAME}/actions/workflows/{settings.WORKFLOW_FILE}/runs?status=queued&per_page=5"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {settings.GH_PAT}", "Accept": "application/vnd.github+json",
                                                   "User-Agent": "kill_pv2"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return int(json.loads(r.read()).get("total_count", 0))
    except Exception:
        return None
