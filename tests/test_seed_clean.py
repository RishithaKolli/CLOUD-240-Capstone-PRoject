import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import seed_and_clean as sc

WF = os.path.join(os.path.dirname(__file__), "workflows")


def test_seed_then_clean_returns_to_original():
    for name in ("clean.yml", "seeded.yml"):
        src = os.path.join(WF, name)
        original = len(sc.scan(src))
        with tempfile.TemporaryDirectory() as d:
            sp = os.path.join(d, "s.yml"); cp = os.path.join(d, "c.yml")
            sc.dump_yaml(sc.seed(sc.load_yaml(src)), sp)
            seeded = len(sc.scan(sp))
            sc.dump_yaml(sc.clean(sc.load_yaml(sp)), cp)
            cleaned = len(sc.scan(cp))
        assert seeded > original          # seeding adds detectable issues
        assert cleaned == original        # cleaning removes exactly what was added
