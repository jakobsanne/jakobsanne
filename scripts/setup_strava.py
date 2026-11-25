#!/usr/bin/env python3
"""One-time setup: authorize your Strava API app and store its keys as GitHub Actions secrets.

Run it yourself in a terminal (it asks for input). Nothing is printed or written to disk:
the keys go straight from Strava to `gh secret set`.

Before running, create an API app at https://www.strava.com/settings/api with
"Authorization Callback Domain" set to `localhost`.
"""

import getpass
import json
import subprocess
import sys
import urllib.parse
import urllib.request

REPO = "jakobsanne/jakobsanne"


def main() -> None:
    client_id = input("Strava Client ID: ").strip()
    client_secret = getpass.getpass("Strava Client Secret (hidden): ").strip()

    authorize = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": "http://localhost",
        "approval_prompt": "force",
        "scope": "activity:read",
    })
    print("\n1. Open this URL in your browser and click Authorize:\n")
    print(f"   {authorize}\n")
    print("2. The browser then goes to a localhost page that won't load. That's expected.")
    print("   Copy the value after 'code=' from its address bar (up to the next '&').\n")
    code = input("Code: ").strip()

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request("https://www.strava.com/oauth/token", data=data),
                                    timeout=30) as resp:
            refresh_token = json.load(resp)["refresh_token"]
    except Exception as exc:
        sys.exit(f"Token exchange failed ({exc}). Check the Client ID/Secret and use a fresh code.")

    for name, value in (("STRAVA_CLIENT_ID", client_id),
                        ("STRAVA_CLIENT_SECRET", client_secret),
                        ("STRAVA_REFRESH_TOKEN", refresh_token)):
        subprocess.run(["gh", "secret", "set", name, "--repo", REPO], input=value.encode(), check=True)

    subprocess.run(["gh", "workflow", "run", "strava.yml", "--repo", REPO], check=True)
    print(f"\nDone. Secrets saved and the first run started: https://github.com/{REPO}/actions")


if __name__ == "__main__":
    main()
