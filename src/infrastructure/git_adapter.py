"""Infrastructure Adapter: Local Git Repository Interface."""
import subprocess
from typing import Tuple


class LocalGitAdapter:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def get_working_diff(self) -> str:
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            return res.stdout
        except Exception:
            return ""

    def run_tests(self) -> Tuple[bool, str]:
        try:
            res = subprocess.run(
                ["pytest", "tests/unit"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            passed = res.returncode == 0
            return passed, res.stdout or res.stderr
        except Exception as ex:
            return False, str(ex)
