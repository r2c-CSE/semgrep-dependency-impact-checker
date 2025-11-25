#!/usr/bin/env python3
"""
Read hardcoded input.csv (columns: dependency,version), query Semgrep's
POST /deployments/{deploymentId}/dependencies/repositories per row, and
write hardcoded output.csv with an added 'Impact' column:
  - "Yes" if ANY repository is returned for that dependency/version
  - "No" otherwise

Auth: set SEMGREP_API_TOKEN env var (Web API scope) or add a --token flag.
"""

import csv
import json
import os
import sys
import time
from typing import Dict, Optional

import requests

# ====== HARD-CODED SETTINGS (edit as needed) ==========================
API_BASE = "https://semgrep.dev/api/v1"
DEPLOYMENT_ID = None  # Will be looked up dynamically via /deployments unless overridden
PAGE_SIZE = 100
INPUT_CSV = "input.csv"
OUTPUT_CSV = "output.csv"
# =====================================================================


def resolve_deployment_id(token: str) -> str:
    """
    Determine which deployment_id to use.
    Priority:
      1) Hardcoded DEPLOYMENT_ID constant if set (not None).
      2) SEMGREP_DEPLOYMENT_ID environment variable, if present.
      3) First deployment returned by GET /deployments.
    """
    if DEPLOYMENT_ID:
        return str(DEPLOYMENT_ID)

    env_dep = os.getenv("SEMGREP_DEPLOYMENT_ID")
    if env_dep:
        return env_dep

    url = f"{API_BASE}/deployments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    try:
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching deployments: {e}", file=sys.stderr)
        raise

    data: Dict = resp.json()  # type: ignore[assignment]
    deployments = data.get("deployments") if isinstance(data, dict) else data
    if deployments is None:
        deployments = data.get("results") if isinstance(data, dict) else data

    if not deployments:
        raise RuntimeError(
            "No deployments returned by /deployments; cannot determine deployment_id"
        )

    first = deployments[0]
    dep_id = first.get("id") or first.get("deploymentId") or first.get("slug")
    if not dep_id:
        raise RuntimeError(
            "Could not find a deployment identifier in /deployments response"
        )

    return str(dep_id)


def clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    v = str(s).strip()
    # Tidy spreadsheet artifacts (e.g., trailing commas, stray equals)
    v = v.strip().strip(",")
    # If version has leading comparison operators (==, =, ~, etc.), strip them.
    if any(v.startswith(op) for op in ("==", ">=", "<=", "~=", "~", "^", "=")):
        v = v.lstrip("=<>~^ ").strip()
    return v or None


def any_repo_matches(
    token: str,
    deployment_id: str,
    dependency_name: Optional[str],
    dependency_version: Optional[str],
    max_retries: int = 3,
    retry_backoff_seconds: float = 2.0,
) -> bool:
    """
    Calls POST /deployments/{deploymentId}/dependencies/repositories with a dependencyFilter.
    Follows cursor pagination until no more results. Returns True if ANY repositories found.
    """
    url = f"{API_BASE}/deployments/{deployment_id}/dependencies/repositories"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    body: Dict = {"page_size": PAGE_SIZE}
    if dependency_name or dependency_version:
        body["dependencyFilter"] = {}
        if dependency_name:
            body["dependencyFilter"]["name"] = dependency_name
        if dependency_version:
            body["dependencyFilter"]["version"] = dependency_version

    cursor = None
    session = requests.Session()

    while True:
        if cursor is not None:
            body["cursor"] = cursor

        # simple retry on transient issues
        for attempt in range(1, max_retries + 1):
            try:
                resp = session.post(url, headers=headers, json=body, timeout=60)
                if 400 <= resp.status_code < 500:
                    # Treat client errors as non-impact and continue (surface brief notice).
                    print(
                        f"Warning: client error {resp.status_code} for "
                        f"{dependency_name} {dependency_version}: {resp.text}",
                        file=sys.stderr,
                    )
                    return False
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.RequestException as e:
                print(
                    f"Warning: request error (attempt {attempt}) for "
                    f"{dependency_name} {dependency_version}: {e}",
                    file=sys.stderr,
                )
                if attempt == max_retries:
                    print(
                        f"Error: giving up on {dependency_name} {dependency_version}: {e}",
                        file=sys.stderr,
                    )
                    return False
                time.sleep(retry_backoff_seconds * attempt)

        # Default/known keys: your example shows 'repositorySummaries'
        repos = (
            data.get("repositorySummaries")
            or data.get("repositories")
            or data.get("results")
            or []
        )
        if repos:
            return True

        cursor = data.get("cursor")
        has_more = data.get("hasMore")
        if not cursor and not has_more:
            break

    return False


def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="Produce output.csv with Impact=Yes/No based on Semgrep dependency presence."
    )
    ap.add_argument(
        "--token",
        help="Semgrep API token (Web API scope). If omitted, uses SEMGREP_API_TOKEN env var.",
    )
    args = ap.parse_args()

    token = args.token or os.getenv("SEMGREP_API_TOKEN")
    if not token:
        print("Error: provide --token or set SEMGREP_API_TOKEN", file=sys.stderr)
        sys.exit(2)

    deployment_id = resolve_deployment_id(token)
    print(f"Using deployment_id={deployment_id}", file=sys.stderr)

    # Read input.csv
    try:
        with open(INPUT_CSV, newline="", encoding="utf-8") as f_in:
            reader = csv.DictReader(f_in)
            if not reader.fieldnames:
                print("Error: input.csv has no header.", file=sys.stderr)
                sys.exit(2)

            # Normalize headers (accept 'dependency' or 'name' for the name column)
            lower_map = {h.lower(): h for h in reader.fieldnames}
            name_key = lower_map.get("dependency") or lower_map.get("name")
            version_key = lower_map.get("version")

            if not name_key:
                print(
                    "Error: input.csv must include a 'dependency' or 'name' column.",
                    file=sys.stderr,
                )
                sys.exit(2)

            # Prepare output.csv: preserve original order + add Impact
            out_fields = list(reader.fieldnames)
            if "Impact" not in out_fields:
                out_fields.append("Impact")

            with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f_out:
                writer = csv.DictWriter(f_out, fieldnames=out_fields)
                writer.writeheader()

                for i, row in enumerate(reader, start=2):
                    dep_name = clean(row.get(name_key))
                    dep_ver = clean(row.get(version_key)) if version_key else None

                    # Pass-through original row values to keep formatting
                    out_row = dict(row)

                    # Skip totally blank lines (but still echo them through with empty Impact)
                    if not dep_name and not dep_ver:
                        out_row["Impact"] = ""
                        writer.writerow(out_row)
                        continue

                    # Progress output
                    print(
                        f"Row {i}: checking {dep_name or '<no name>'} {dep_ver or ''}...",
                        file=sys.stderr,
                    )

                    impacted = any_repo_matches(
                        token=token,
                        deployment_id=deployment_id,
                        dependency_name=dep_name,
                        dependency_version=dep_ver,
                    )


                    # ---- NEW: Print alert if matched ----
                    if impacted:
                        print(
                            f"🚨 IMPACT MATCH: {dep_name} {dep_ver or ''} appears in your deployment!",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"OK: no match for {dep_name} {dep_ver or ''}",
                            file=sys.stderr,
                        )
                    # --------------------------------------


                    out_row["Impact"] = "Yes" if impacted else "No"
                    writer.writerow(out_row)

    except FileNotFoundError:
        print(f"Error: '{INPUT_CSV}' not found in the working directory.", file=sys.stderr)
        sys.exit(2)

    print(f"Done. Wrote: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
