"""Common intermediate representation produced by every parser."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CAPTION_FIG = re.compile(r"^\s*(그림|Figure|Fig\.?)\s*[\d\-\.]+", re.I)
CAPTION_TBL = re.compile(r"^\s*(표|Table|Tab\.?)\s*[\d\-\.]+", re.I)
HEADING_NUM = re.compile(r"^\s*(\d+(?:\.\d+){0,5})\.?\s+(\S.*)$")


@dataclass
class Block:
    kind: str                      # heading | para | table | figure
    text: str = ""
    level: int = 0                 # heading level (1..6)
    number: str = ""               # heading number, e.g. "3.2.1"
    loc: str = ""                  # "p.4" / "para 37"
    style: str = ""
    # table: grid = list of rows, each a list of cells {"t": text, "rs": rowspan, "cs": colspan, "skip": bool}
    grid: list = field(default_factory=list)
    caption: str = ""
    # figure
    image: bytes | None = None
    image_ext: str = ""            # png / jpg / emf / wmf ...
    list_level: int = -1           # >=0 when the paragraph is a list item
    # structured sources (ReqIF): object identity and attributes that travel with the block
    meta: dict = field(default_factory=dict)

    def table_values(self) -> list[list[str]]:
        """Grid with merged cells filled in (every row has the same number of columns)."""
        out = []
        for row in self.grid:
            out.append([c.get("t", "") for c in row])
        return out


def norm_text(s: str) -> str:
    s = s.replace(" ", " ").replace("​", "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def grid_from_matrix(rows: list[list[str | None]]) -> list[list[dict]]:
    """Build a grid from a value matrix where None marks a cell merged into its left/upper neighbour
    (pdfplumber convention). Merged cells are filled with the owner's text and flagged skip=True."""
    if not rows:
        return []
    ncol = max(len(r) for r in rows)
    mat = [list(r) + [""] * (ncol - len(r)) for r in rows]
    grid = [[{"t": "", "rs": 1, "cs": 1, "skip": False} for _ in range(ncol)] for _ in mat]
    for i, r in enumerate(mat):
        for j, v in enumerate(r):
            if v is None:
                # pdfplumber marks both horizontal and vertical merges with None.
                # First column, or left neighbour itself vertically merged -> vertical merge; else horizontal.
                left_vertical = j > 0 and grid[i][j - 1].get("dir") == "v"
                if j > 0 and not left_vertical:
                    owner = grid[i][j - 1].get("owner", (i, j - 1))
                    grid[i][j] = {"t": grid[owner[0]][owner[1]]["t"], "skip": True, "owner": owner, "dir": "h"}
                    grid[owner[0]][owner[1]]["cs"] = max(grid[owner[0]][owner[1]]["cs"], j - owner[1] + 1)
                elif i > 0:
                    owner = grid[i - 1][j].get("owner", (i - 1, j))
                    grid[i][j] = {"t": grid[owner[0]][owner[1]]["t"], "skip": True, "owner": owner, "dir": "v"}
                    grid[owner[0]][owner[1]]["rs"] = max(grid[owner[0]][owner[1]]["rs"], i - owner[0] + 1)
                else:
                    grid[i][j] = {"t": "", "rs": 1, "cs": 1, "skip": False}
            else:
                grid[i][j] = {"t": norm_text(str(v)), "rs": 1, "cs": 1, "skip": False}
    for row in grid:
        for c in row:
            c.pop("owner", None)
            c.pop("dir", None)
    return grid
