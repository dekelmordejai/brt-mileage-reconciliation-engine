"""Guard public Git content against accidental private runtime artifacts."""

import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
problems = []
for name in files:
    p = Path(name)
    if any(
        part
        in {
            "private_data",
            "case_studies",
            "internal",
            "legacy",
            "work",
            "outputs",
            ".venv",
            "test-results",
        }
        for part in p.parts
    ):
        problems.append(name + ": private artifact directory")
    if p.suffix.lower() in {
        ".db",
        ".sqlite",
        ".sqlite3",
        ".pkl",
        ".xlsx",
        ".xls",
        ".pdf",
        ".zip",
        ".mp4",
        ".avi",
        ".log",
        ".pem",
        ".key",
    }:
        problems.append(name + ": prohibited artifact type")
    if name.startswith(".env") and name != ".env.example":
        problems.append(name + ": environment secrets file")
    if p.suffix.lower() == ".csv" and not name.startswith(("examples/synthetic/", "fixtures/")):
        problems.append(name + ": CSV outside synthetic allowlist")
    if p.suffix.lower() in {".png", ".jpg", ".jpeg"} and name != "docs/assets/demo-dashboard.png":
        problems.append(name + ": image outside reviewed synthetic screenshot allowlist")
    if p.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        text = (root / p).read_text(encoding="utf-8")
        if re.search(
            r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----",
            text,
        ):
            problems.append(name + ": possible credential")
        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        if any(not address.endswith("@users.noreply.github.com") for address in emails):
            problems.append(name + ": email address needs explicit public review")
if problems:
    raise SystemExit("\n".join(problems))
print(
    f"Public-content guard passed for {len(files)} tracked files. Manual review is still required."
)
