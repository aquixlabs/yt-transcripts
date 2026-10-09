"""
Prove the tests can fail: break each status decision, one at a time, and
require the offline suite to catch it. Every file is restored and its hash
checked after each mutation. Bytecode is disabled, so a stale .pyc cannot
serve the unmutated code and make a mutation look caught or missed.

    python tools/mutation_check.py
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = "src/yt_transcripts/core.py"
APIFY = "src/yt_transcripts/apify.py"
INIT = "src/yt_transcripts/__init__.py"

MUTATIONS = [
    # (status guarded, file, original, mutated)
    ("OK", CORE, "        status=OK, video_id=video_id, language=fetched.language,",
     "        status=ERROR, video_id=video_id, language=fetched.language,"),
    ("NO_CAPTIONS", CORE, 'return res(NO_CAPTIONS, "YouTube served the video',
     'return res(BLOCKED, "YouTube served the video'),
    ("NO_CAPTIONS guard: refusals", CORE, "if refusal is None and not _tracks(player):",
     "if True:"),
    ("NO_CAPTIONS guard: videoDetails", CORE,
     'if (player.get("videoDetails") or {}).get("videoId") != video_id:', "if False:"),
    ("BLOCKED: captcha", CORE, 'return res(BLOCKED, "YouTube served a captcha',
     'return res(ERROR, "YouTube served a captcha'),
    ("BLOCKED: bot check", CORE, 'return res(BLOCKED, "YouTube asked this machine',
     'return res(ERROR, "YouTube asked this machine'),
    ("BLOCKED: PoToken", CORE, 'return res(BLOCKED, "YouTube demands a proof-of-origin',
     'return res(ERROR, "YouTube demands a proof-of-origin'),
    ("BLOCKED: geo before removed", CORE,
     '(BLOCKED, ("not a bot", "in your country", "not made this video available")),',
     '(BLOCKED, ("not a bot",)),'),
    ("BLOCKED: empty track", CORE,
     "            status=BLOCKED, video_id=video_id, language=fetched.language,",
     "            status=NO_CAPTIONS, video_id=video_id, language=fetched.language,"),
    ("BLOCKED: 403", CORE, 'return res(BLOCKED, f"YouTube refused the request',
     'return res(ERROR, f"YouTube refused the request'),
    ("RATE_LIMITED", CORE, "if 429 in list(statuses):", "if False:"),
    ("AGE_RESTRICTED", CORE, 'return res(AGE_RESTRICTED, "YouTube requires',
     'return res(ERROR, "YouTube requires'),
    ("PRIVATE", CORE, '(PRIVATE, ("video is private"', '(REMOVED, ("video is private"'),
    ("REMOVED", CORE, 'return res(REMOVED, "YouTube says the video is unavailable',
     'return res(ERROR, "YouTube says the video is unavailable'),
    ("LANGUAGE_UNAVAILABLE", CORE, "return res(LANGUAGE_UNAVAILABLE,",
     "return res(NO_CAPTIONS,"),
    ("ERROR: unknown reason", CORE, 'return res(ERROR, f"YouTube will not play',
     'return res(BLOCKED, f"YouTube will not play'),
    ("ERROR: network", CORE, 'return res(ERROR, f"could not reach YouTube',
     'return res(NO_CAPTIONS, f"could not reach YouTube'),
    ("apify: status map", APIFY, '"UNAVAILABLE: REMOVED": REMOVED,',
     '"UNAVAILABLE: REMOVED": NO_CAPTIONS,'),
    ("apify: spend cap sent", APIFY, '"maxTotalChargeUsd":', '"maxTotalCharge":'),
    ("apify: abort on timeout", APIFY, 'http.post(f"{API}/actor-runs/{run_id}/abort"',
     'None and http.post(f"{API}/actor-runs/{run_id}/abort"'),
    ("apify: only when asked", INIT, "if result.status not in HANDOFF or not apify:",
     "if result.status not in HANDOFF:"),
]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def suite_passes():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("APIFY_TOKEN", None)
    p = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    return p.returncode == 0


def main():
    if not suite_passes():
        print("the unmutated suite fails; fix that first")
        return 2
    survived = []
    for label, rel, old, new in MUTATIONS:
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        before = sha(path)
        if src.count(old) != 1:
            print(f"  ?    {label}: anchor found {src.count(old)}x in {rel}")
            survived.append(label)
            continue
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(src.replace(old, new))
            caught = not suite_passes()
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
        assert sha(path) == before, f"{rel} was not restored"
        print(("  killed   " if caught else "  SURVIVED ") + label)
        if not caught:
            survived.append(label)
    print(f"\n{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} mutations caught; "
          "all files restored and hash-verified")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
