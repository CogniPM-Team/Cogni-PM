"""Live proof of the whole MVP flow through the API, against your real Jira project and real Gemini.

It starts the API itself (with a throwaway database unless DATABASE_URL is set) and then plays the part of the
frontend over HTTP:

  1. asks the Co-Pilot a question (M1, read only)
  2. starts a P1 run over synthetic planning notes and waits for it to be ready for review
  3. edits the first draft, then approves ONLY that one (the other is dropped, not created)
  4. checks the real issue in Jira: the PM's wording, the cognipm-drafted label, the stamp, the comment
  5. approves again, which must be refused, and shows the activity log
  6. closes the issue it made (the API user cannot delete) so nothing stays open in your project

WRITES TO YOUR REAL JIRA PROJECT and SENDS TEXT TO GEMINI (synthetic notes only). It creates one issue,
labelled cognipm-sandbox and then closed, and uses one issue number that Jira never reuses. It refuses to run
without --confirm. Needs GEMINI_API_KEY and the JIRA_* values in .env. Run from backend/:

    python scripts/demo_flow.py --confirm
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time

import httpx

from cognipm.config import BACKEND_DIR
from cognipm.gateway.jira import SANDBOX_LABEL, JiraClient, JiraConfigError

NOTES = """\
Notes from the planning call (synthetic example, not real project data).

Support keeps getting tickets from customers who forgot their password. Customers should be able to
reset their password themselves by email. The reset link must expire after one hour.

Finance wants a monthly CSV export of all invoices so they can reconcile against the bank. It only
needs to include paid and overdue invoices.
"""
MARK = "[CogniPM demo] "


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_api(base: str, process: subprocess.Popen) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("the API process exited during startup")
        try:
            if httpx.get(f"{base}/api/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError("the API did not become ready")


def ok(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} -> {response.status_code}: {response.text[:300]}"
        )
    return response.json()


def wait_for_review(api: httpx.Client, run_id: str) -> dict:
    for _ in range(240):
        detail = ok(api.get(f"/api/runs/{run_id}"))
        if detail["run"]["status"] != "running":
            return detail
        time.sleep(1)
    raise RuntimeError("the run did not finish in four minutes")


def flow(api: httpx.Client, jira: JiraClient, created_keys: list[str]) -> bool:
    modes = ok(api.get("/api/modes"))
    print("Modes:", ", ".join(f"{m['id']} {m['name']} ({len(m['tools'])} tools)" for m in modes))

    print("\n1. Co-Pilot (M1, read only)")
    chat = ok(
        api.post("/api/chat", json={"message": "In one sentence, how many issues does the project have?"})
    )
    print(f"   {chat['answer']}  [{len(chat['tool_calls'])} read(s)]")

    print("\n2. P1 run over the synthetic notes")
    started = ok(api.post("/api/runs", json={"task": "p1", "input_text": NOTES}))
    detail = wait_for_review(api, started["run_id"])
    print(f"   run {detail['run']['id']}: {detail['run']['status']}; {detail['status_note']}")
    for draft in detail["drafts"]:
        span = draft["sources"][0]
        quoted = (
            detail["input_text"][span["start"] : span["end"]]
            if span["start"] is not None
            else "(not located)"
        )
        print(
            f"   - {draft['effective']['summary']}\n       first cited quote, found in the input: {quoted!r}"
        )
    if detail["run"]["status"] != "awaiting_review" or len(detail["drafts"]) < 2:
        print("   Expected two drafts awaiting review.")
        return False

    print("\n3. Edit the first draft, then approve only that one")
    first, second = detail["drafts"][0], detail["drafts"][1]
    edited = ok(
        api.patch(f"/api/changes/{first['id']}", json={"summary": MARK + first["effective"]["summary"]})
    )
    print(f"   edited: {first['effective']['summary']!r} -> {edited['effective']['summary']!r}")
    approval = ok(api.post(f"/api/runs/{detail['run']['id']}/approve", json={"change_ids": [first["id"]]}))
    created_keys.extend(c["issue_key"] for c in approval["created"])
    print(f"   created {created_keys}; dropped {len(approval['dropped'])} draft (not created)")

    print("\n4. The real issue in Jira")
    issue = jira.get_issue(created_keys[0])
    print(f"   {issue.key} [{issue.issue_type}] {issue.summary!r}  labels={issue.labels}")
    checks = {
        "has the PM's wording": issue.summary == edited["effective"]["summary"],
        "labelled cognipm-drafted": "cognipm-drafted" in issue.labels,
        "stamped with its draft id": f"cognipm-draft-{first['id']}" in issue.labels,
        "the dropped draft was not created": second["id"] not in str(issue.labels),
    }
    for name, passed in checks.items():
        print(f"   {'ok ' if passed else 'BAD'} {name}")

    print("\n5. Approving the same run again must be refused")
    again = api.post(f"/api/runs/{detail['run']['id']}/approve")
    print(f"   -> {again.status_code}: {again.json().get('detail')}")
    log = ok(api.get("/api/audit", params={"filter": "changed_jira"}))["rows"]
    print(f"   activity log, 'changed Jira': {[r['detail'] for r in log]}")
    return all(checks.values()) and again.status_code == 409


def main() -> int:
    if "--confirm" not in sys.argv[1:]:
        print(__doc__)
        print("Not run: pass --confirm to proceed.")
        return 2
    try:
        jira = JiraClient()
    except JiraConfigError as exc:
        print(f"Config error: {exc}")
        return 1
    if not os.environ.get("GEMINI_API_KEY"):
        print("Set GEMINI_API_KEY in .env.")
        return 1

    env = dict(os.environ)
    cleanup = []
    if not env.get("DATABASE_URL"):
        try:
            import pgserver
        except ImportError:
            print("Set DATABASE_URL, or pip install -e '.[embedded-db]' for a throwaway database.")
            return 1
        data_dir = tempfile.TemporaryDirectory()
        server = pgserver.get_server(data_dir.name, cleanup_mode="stop")
        env["DATABASE_URL"] = server.get_uri()
        cleanup += [server.cleanup, data_dir.cleanup]

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "cognipm.api.main:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
    )
    created_keys: list[str] = []
    passed = False
    try:
        wait_for_api(base, process)
        with jira, httpx.Client(base_url=base, timeout=120) as api:
            try:
                passed = flow(api, jira, created_keys)
            finally:
                for (
                    key
                ) in created_keys:  # the API user cannot delete, so label then close what this script made
                    try:
                        labels = jira.get_issue(key).labels
                        jira.update_issue_fields(key, {"labels": [*labels, SANDBOX_LABEL]})
                        print(f"\nCleanup: closed {key} via {jira.close_issue(key)!r}")
                    except Exception as exc:  # noqa: BLE001 - tell the human what to do
                        print(f"\nCLEANUP FAILED for {key}: {exc}. Close it by hand in Jira.")
                        passed = False
    except Exception as exc:  # noqa: BLE001 - report plainly
        print(f"\nFailed: {exc}")
    finally:
        process.terminate()
        process.wait(timeout=15)
        for step in cleanup:
            step()

    print("\nPASS: the whole flow worked against the real site." if passed else "\nFAIL: see messages above.")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
