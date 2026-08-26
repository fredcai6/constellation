"""The code map's off-path: what happens when it is pointed somewhere wrong.

`tools/code_map` is decoupled from the engine -- no verb, no step, no import --
but it is run by hand from the palette, and the way an agent meets it wrong is
by pointing `--root` at the wrong directory. Discovery shells out to
`git ls-files`, so that is where a bad root surfaces. A traceback there says
nothing about what to do next, which `test_robustness.py` already forbids of
every other off-path in this repo.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.code_map import cli  # noqa: E402


def test_outside_a_checkout_the_generator_refuses_instead_of_crashing(tmp_path):
    for argv, want in [
        (["discover", "--root", str(tmp_path)], "is not a git checkout"),
        (["build", "--root", str(tmp_path),
          "--artifacts", str(tmp_path / "a"), "--out", str(tmp_path / "o")],
         "is not a git checkout"),
        (["discover", "--root", str(tmp_path / "nosuchdir")], "is not a directory"),
    ]:
        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        msg = str(e.value)
        assert want in msg
        assert "--root" in msg      # and the refusal names the way forward
