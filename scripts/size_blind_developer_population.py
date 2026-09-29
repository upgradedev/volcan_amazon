"""How many US software developers report a vision difficulty: the ACS 2024 cross-tab.

The US Census Bureau publishes employed people with a vision difficulty (table
B18120) and software developers (table B24114) as separate tables. Neither
crosses the two, so this script reads the American Community Survey 2024
1-year Public Use Microdata Sample person file itself and counts the civilian
employed (ESR 1 or 2) whose occupation is Software Developers (OCCP 1021) and
who answered yes to the vision difficulty question (DEYE 1). The Census
definition of that question: "blind or having serious difficulty seeing, even
when wearing glasses". It is broader than screen-reader use, so the count is an
upper bound on Volcan's users, not a count of blind developers.

Run command:
    python scripts/size_blind_developer_population.py

It streams the 603 MB zip with HTTP range requests and keeps nothing on disk,
so it needs a network connection and a few minutes. Standard errors use the
successive difference replicate method over the 80 person replicate weights,
SE = sqrt(4/80 * sum((replicate - estimate)^2)), which the Census 2024 PUMS
accuracy statement recommends; its 90% margin of error is 1.645 * SE. As a check, the weighted developer total should fall within the
published margin of B24114_068E (2,293,639 +/- 30,857 for 2024).

Printed on 2026-09-28: 21,808 developer records, 171 of them with a vision
difficulty, weighting to 17,933 (90% MOE +/- 2,686) of 2,314,223 developers,
or 0.775% (SE 0.071 points).
"""
import csv
import io
import json
import math
import sys
import urllib.request
import zipfile

PUMS_URL = "https://www2.census.gov/programs-surveys/acs/data/pums/2024/1-Year/csv_pus.zip"
SOFTWARE_DEVELOPERS = "1021"
CIVILIAN_EMPLOYED = ("1", "2")
REPLICATES = 80


class RangeFile(io.RawIOBase):
    """A read-only, seekable view of a remote file, fetched in large ranges."""

    def __init__(self, url: str, block: int = 16 << 20) -> None:
        self.url, self.pos, self.block = url, 0, block
        head = urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=120)
        self.size = int(head.headers["Content-Length"])
        self.buf_start, self.buf = -1, b""

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self.pos, 2: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def _fill(self, start: int) -> None:
        end = min(self.size, start + self.block) - 1
        last_error: Exception | None = None
        for _ in range(5):
            try:
                request = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}"})
                self.buf = urllib.request.urlopen(request, timeout=120).read()
                self.buf_start = start
                return
            except OSError as error:
                last_error = error
        raise RuntimeError(f"range {start}-{end} failed: {last_error}")

    def readinto(self, target) -> int:
        wanted, done = len(target), 0
        while done < wanted and self.pos < self.size:
            if not (self.buf_start <= self.pos < self.buf_start + len(self.buf)):
                self._fill(self.pos)
            offset = self.pos - self.buf_start
            chunk = self.buf[offset:offset + wanted - done]
            target[done:done + len(chunk)] = chunk
            done += len(chunk)
            self.pos += len(chunk)
        return done


def replicate_se(values: list[float]) -> float:
    return math.sqrt(4 / REPLICATES * sum((values[k] - values[0]) ** 2 for k in range(1, REPLICATES + 1)))


def main() -> int:
    archive = zipfile.ZipFile(io.BufferedReader(RangeFile(PUMS_URL), 1 << 20))
    developers = [0.0] * (REPLICATES + 1)
    with_vision = [0.0] * (REPLICATES + 1)
    rows = developer_records = vision_records = 0
    for name in (n for n in archive.namelist() if n.endswith(".csv")):
        with archive.open(name) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"))
            header = {column: i for i, column in enumerate(next(reader))}
            weights = [header["PWGTP"]] + [header[f"PWGTP{k}"] for k in range(1, REPLICATES + 1)]
            occupation, vision, employment = header["OCCP"], header["DEYE"], header["ESR"]
            for row in reader:
                rows += 1
                if row[occupation] != SOFTWARE_DEVELOPERS or row[employment] not in CIVILIAN_EMPLOYED:
                    continue
                w = [float(row[i]) for i in weights]
                developer_records += 1
                developers = [a + b for a, b in zip(developers, w)]
                if row[vision] == "1":
                    vision_records += 1
                    with_vision = [a + b for a, b in zip(with_vision, w)]
        print(f"read {name}: {rows} person rows so far", file=sys.stderr)
    share = [v / d for v, d in zip(with_vision, developers)]
    result = {
        "source": PUMS_URL,
        "person_rows": rows,
        "software_developer_records": developer_records,
        "records_with_vision_difficulty": vision_records,
        "software_developers": round(developers[0]),
        "software_developers_moe90": round(1.645 * replicate_se(developers)),
        "with_vision_difficulty": round(with_vision[0]),
        "with_vision_difficulty_moe90": round(1.645 * replicate_se(with_vision)),
        "share_percent": round(100 * share[0], 3),
        "share_percent_se": round(100 * replicate_se(share), 3),
    }
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
