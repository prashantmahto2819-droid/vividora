"""The admin guide covers every key / switch of API & Keys, and docs/admin-guide.md is the current output.
Run: python3 tests/test_adminguide.py   (after changing adminguide.py: python3 -m vividora.adminguide)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vividora import adminguide, provkeys  # noqa: E402


def main():
    envs = [c["env"] for c in provkeys.CATALOG]
    missing = [e for e in envs if len(adminguide.HELP.get(e, [])) < 2]
    assert not missing, f"no on/off explanation for: {missing}"
    extra = [e for e in adminguide.HELP if e not in envs]
    assert not extra, f"explained but not in API & Keys: {extra}"
    for c in provkeys.CATALOG:                       # every choice of a switch is named in its explanation or in the task table
        if c.get("choices"):
            assert len(adminguide.HELP[c["env"]]) >= len(c["choices"]) - 1, c["env"]
    d = adminguide.data()
    assert len(d["tasks"]) >= 8 and all(t["options"] for t in d["tasks"]) and len(d["checklist"]) >= 8
    labels = {c["label"].split(" (")[0] for c in provkeys.CATALOG}
    for t in d["tasks"]:                             # a switch named in the task table really exists
        for o in t["options"]:
            if " = " in o["switch"]:
                name = o["switch"].split(" = ")[0]
                assert any(name.startswith(l_) or l_.startswith(name) for l_ in labels), f"unknown switch in the guide: {name}"
    md = Path(__file__).resolve().parents[2] / "docs" / "admin-guide.md"
    assert md.read_text(encoding="utf-8") == adminguide.markdown(), "docs/admin-guide.md is out of date — run: python3 -m vividora.adminguide"
    st = provkeys.status()
    assert all(r["help"] for r in st)
    print(f"admin guide: {len(envs)} keys / switches explained, {len(d['tasks'])} jobs mapped, docs/admin-guide.md current ✓")
    print("ALL PASS")


if __name__ == "__main__":
    main()
