# README.md

## 📌 Overview

This repository contains a Python script (`npm_impact.py`) that checks whether the dependencies listed in `input.csv` appear in any repositories of your Semgrep deployment.

The script:

- Reads `input.csv` with columns:  
  **dependency**, **version**
- Queries the Semgrep Web API:
  - `GET /deployments` → to determine your `deployment_id`
  - `POST /deployments/{deployment_id}/dependencies/repositories` → to check usage
- Writes `output.csv` with an extra column **Impact** ("Yes" / "No")
- Prints progress and alerts for matched dependencies

---

## 🛠️ Requirements

- Python **3.8+**
- The following Python packages:
  ```
  requests
  ```

Install dependencies:

```bash
pip install -r requirements.txt
```

(Or install manually: `pip install requests`)

---

## 🔑 Environment Variables

Before running the script, you **must** export your Semgrep Web API token.

The token must have **Web API** scope.

```bash
export SEMGREP_API_TOKEN="your_web_api_token_here"
```

If you skip this step, the script will stop immediately.

---

## 📥 Input Format

Create an `input.csv` with:

| dependency | version |
|-----------|---------|
| lodash    | 4.17.21 |
| express   | 4.18.2  |

Notes:
- Column names must be exactly `dependency` and `version` (case-insensitive).
- Extra columns are preserved in the output.

---

## ▶️ Running the Script

From the same directory:

```bash
python npm_impact.py
```

### Optional flags

You can also pass a token explicitly:

```bash
python npm_impact.py --token $SEMGREP_API_TOKEN
```

(This overrides the environment variable – useful for CI.)

---

## 📤 Output

The script writes `output.csv` with all original columns + a final **Impact** column:

| dependency | version | Impact |
|-----------|---------|--------|
| lodash    | 4.17.21 | Yes    |
| express   | 4.18.2  | No     |

---

## 🔔 Progress & Alerts

During execution, the script prints progress to **stderr**, for example:

```
Using deployment_id=56359
Row 2: checking lodash 4.17.21...
🚨 IMPACT MATCH: lodash 4.17.21 appears in your deployment!
Row 3: checking express 4.18.2...
OK: no match for express 4.18.2
```

This makes long runs transparent without polluting the CSV output.

---

## 🧩 How Deployment ID Is Determined

The script automatically resolves the deployment ID by:

1. Using a hardcoded `DEPLOYMENT_ID` (if enabled), otherwise
2. Using `SEMGREP_DEPLOYMENT_ID` environment variable (if set), otherwise  
3. Calling `GET /deployments` and selecting the **first** deployment returned.

This avoids hardcoding deployment IDs in the script.

---

## ❗ Troubleshooting

### “Error: provide --token or set SEMGREP_API_TOKEN”
You forgot to export the environment variable.  
Run:

```bash
export SEMGREP_API_TOKEN="..."
```

### “input.csv not found”
Make sure you are running the script from the directory where `input.csv` is located.

### Empty `Impact` column
Check:
- Typo in `dependency` or `version`
- Lockfiles missing in Semgrep deployment
- Wrong Semgrep token (missing Web API scope)

---

## 📄 License

MIT License 
