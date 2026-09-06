"""`run.verdict_fold`: the fold logic obligations 1, 2, 4 and 5 need, proved
in isolation against hand-built returns, panelist forms and outcome tables.
Three inputs, not two: a panel's returns, the panelist form each voice was
dispatched under (positional with `step["panel"]`), and the deciding
segment's own outcome table, shaped like `run.deciding_spec`'s own second
return value.

The differential test that stood here -- the fold's clean word against
`merged_verdict`'s, for every declared panel in the tree -- went out with
`merged_verdict` itself. Its job was to hold the new fold to the old logic
while nothing called the new one; `tests/test_verdict_wiring.py` now drives
the real, and only, fold through real seams instead, which is the stronger
claim and needs no second implementation of the two-word logic to compare
against.
"""

from engine import run as runmod

# A vocabulary-bearing form, shaped like CRITIC.toml / REVIEW.toml: a
# `verdict` field whose note declares `pass | revise`.
VOCAB_FORM = {
    "fields": [
        {"id": "findings", "kind": "evidence", "note": "waived: clean."},
        {"id": "verdict", "kind": "decision", "note": "pass | revise. ..."},
    ]
}

# A second vocabulary-bearing form, under a different vocabulary -- proving
# each voice is read against its own, not one shared word list.
READY_FORM = {
    "fields": [
        {"id": "verdict", "kind": "decision", "note": "ready | changes-needed. ..."},
    ]
}

# PLAN.toml's own case: no `verdict` field anywhere on the form.
NO_VERDICT_FORM = {
    "fields": [
        {"id": "plan", "kind": "artifact", "note": "Point at it."},
        {"id": "purpose", "kind": "evidence", "note": "What this gate accomplishes."},
    ]
}

# The one real seam in this tree whose words are the table's whole
# vocabulary: assemblies/explore-an-idea/ASSEMBLY.toml:69-75.
PASS_REVISE_TABLE = {"outcome": [
    {"value": "pass", "does": "release"},
    {"value": "revise", "does": "rework"},
]}


def _ret(child, verdict=None, fields=None):
    f = dict(fields) if fields is not None else ({} if verdict is None else {"verdict": verdict})
    return {"child": child, "fields": f}


# -- single-voice cases (1, 3, 4, 5, 6, 7) -----------------------------------


def test_case_1_every_voice_passes():
    returns = [_ret("w.step.p1", "pass")]
    assert runmod.verdict_fold(returns, [VOCAB_FORM], PASS_REVISE_TABLE) == ("clean", "pass")


def test_case_3_empty_fields():
    returns = [_ret("w.step.p1", fields={})]
    outcome = runmod.verdict_fold(returns, [VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome == ("refused", "p1")


def test_case_4_missing_verdict_key():
    returns = [_ret("w.step.p1", fields={"findings": "waived: clean."})]
    outcome = runmod.verdict_fold(returns, [VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome == ("refused", "p1")


def test_case_5_empty_verdict_string():
    returns = [_ret("w.step.p1", verdict="")]
    outcome = runmod.verdict_fold(returns, [VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome == ("refused", "p1")


def test_case_6_word_not_in_vocabulary():
    returns = [_ret("w.step.p1", verdict="maybe")]
    outcome = runmod.verdict_fold(returns, [VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome == ("refused", "p1")


def test_case_7_form_declares_no_verdict_field_resolves_quiet_never_refused():
    # No matter what the return's own fields hold -- even a foreign word or
    # empty fields -- a no-vocabulary form's voice is quiet, not refused.
    for returns in (
        [_ret("w.step.p1", verdict="anything")],
        [_ret("w.step.p1", fields={})],
        [_ret("w.step.p1", verdict="")],
    ):
        assert runmod.verdict_fold(returns, [NO_VERDICT_FORM], PASS_REVISE_TABLE) == ("quiet", None)


def test_case_7_multi_voice_panel_folds_to_quiet_when_every_form_is_wordless():
    # The single-voice case above is not the whole rule: a multi-voice panel
    # -- every voice dispatched under a form with no `verdict` field at all,
    # design-it-twice's rival-planner panel (shelved, #96) having been the
    # tree's one worked example -- must fold panel-wide to quiet too, not
    # just a lone voice. A fold that only recognized quiet for a single-voice
    # panel would pass the case above but fail this one.
    returns = [_ret("w.step.p1", verdict="anything"), _ret("w.step.p2", fields={})]
    outcome = runmod.verdict_fold(returns, [NO_VERDICT_FORM, NO_VERDICT_FORM], PASS_REVISE_TABLE)
    assert outcome == ("quiet", None)


# -- case 2: revise outranks pass by the deciding table, not a literal ------


def test_case_2_revise_outranks_pass_via_declared_does():
    returns = [_ret("w.step.p1", "pass"), _ret("w.step.p2", "revise")]
    outcome = runmod.verdict_fold(returns, [VOCAB_FORM, VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome == ("clean", "revise")
    # order in `returns` does not matter -- the table decides, not arrival
    returns_swapped = [_ret("w.step.p1", "revise"), _ret("w.step.p2", "pass")]
    outcome2 = runmod.verdict_fold(returns_swapped, [VOCAB_FORM, VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome2 == ("clean", "revise")


# -- case 8: two panelists, two different forms, paired by child id --------


def test_case_8_two_voices_two_forms_paired_by_own_pn_index():
    # p1 dispatched under READY_FORM, p2 under VOCAB_FORM -- each return
    # must be read against its own panelist's form, not a shared one and
    # not the returns list zipped against the panel list in arrival order.
    returns = [_ret("w.step.p2", "revise"), _ret("w.step.p1", "ready")]
    outcome = runmod.verdict_fold(returns, [READY_FORM, VOCAB_FORM], PASS_REVISE_TABLE)
    # p1's "ready" is not in VOCAB_FORM's pass|revise vocabulary -- but p1 was
    # dispatched under READY_FORM, whose own vocabulary it *is* in. p2's
    # "revise" is in VOCAB_FORM's vocabulary. Both voices are clean; revise
    # outranks by the table.
    assert outcome == ("clean", "revise")

    # Proof the pairing is by id, not arrival order: if the returns were
    # (wrongly) zipped against the panel list in arrival order, p2's return
    # ("revise") would be checked against panel_forms[0] (READY_FORM), whose
    # vocabulary does not contain "revise" -- a refusal, not a clean revise.
    assert outcome != ("refused", "p2")


# -- case 9: a refusal outranks a co-panelist's clean word ------------------


def test_case_9_refusal_outranks_co_panelists_clean_word():
    returns = [_ret("w.step.p1", verdict="garbage"), _ret("w.step.p2", "pass")]
    outcome = runmod.verdict_fold(returns, [VOCAB_FORM, VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome == ("refused", "p1")
    # order in `returns` does not matter for attribution either -- the
    # refusal names whichever voice's own outcome was "refused", not
    # whichever return happens to sit first in the list. Swap so the clean
    # voice is first and the refusing voice is second: the result must still
    # name p2, the actual refuser, not p1.
    returns_swapped = [_ret("w.step.p1", "pass"), _ret("w.step.p2", verdict="garbage")]
    outcome2 = runmod.verdict_fold(returns_swapped, [VOCAB_FORM, VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome2 == ("refused", "p2")


# -- case 10: a quiet voice paired with a clean vocabulary voice ------------


def test_case_10_no_vocab_voice_with_clean_vocab_voice_folds_to_clean_word():
    returns = [_ret("w.step.p1", verdict="anything"), _ret("w.step.p2", "pass")]
    outcome = runmod.verdict_fold(returns, [NO_VERDICT_FORM, VOCAB_FORM], PASS_REVISE_TABLE)
    assert outcome == ("clean", "pass")
    assert outcome != ("quiet", None)


# -- case 11: ranking follows the table's own declared verbs, not "revise" -


def test_case_11_ranking_follows_declared_does_not_the_word_revise():
    ready_table = {"outcome": [
        {"value": "ready", "does": "release"},
        {"value": "changes-needed", "does": "rework"},
    ]}
    returns = [_ret("w.step.p1", "ready"), _ret("w.step.p2", "changes-needed")]
    outcome = runmod.verdict_fold(returns, [READY_FORM, READY_FORM], ready_table)
    assert outcome == ("clean", "changes-needed")

    # Swap which value the table declares the non-release verb for -- the
    # winner flips with the table, not with either literal word.
    swapped_table = {"outcome": [
        {"value": "ready", "does": "rework"},
        {"value": "changes-needed", "does": "release"},
    ]}
    outcome2 = runmod.verdict_fold(returns, [READY_FORM, READY_FORM], swapped_table)
    assert outcome2 == ("clean", "ready")


# -- case 12: an undeclared clean word never outranks a declared release ---


def test_case_12_undeclared_word_does_not_outrank_declared_release():
    # The table names a row for one word and none at all for the other --
    # `declared_does` answers `None` for the second, which this gate rules
    # the same inert class as an explicit "release" row, never a class
    # above it. The declared row must still win the tie it is actually in.
    table_missing_a_row = {"outcome": [{"value": "pass", "does": "release"}]}
    returns = [_ret("w.step.p1", "pass"), _ret("w.step.p2", "revise")]
    outcome = runmod.verdict_fold(returns, [VOCAB_FORM, VOCAB_FORM], table_missing_a_row)
    assert outcome == ("clean", "pass")
    assert outcome != ("clean", "revise")

    # Order does not rescue the undeclared word either.
    returns_swapped = [_ret("w.step.p1", "revise"), _ret("w.step.p2", "pass")]
    outcome2 = runmod.verdict_fold(returns_swapped, [VOCAB_FORM, VOCAB_FORM], table_missing_a_row)
    assert outcome2 == ("clean", "pass")


# -- case 13: the ranking follows a declared source, never a literal word --


# The same shape as VOCAB_FORM / PASS_REVISE_TABLE, with the passing and
# revising values renamed together in the form and in the table -- proof the
# fold's ranking is read from a declared source and not from the literal
# strings "pass" or "revise" anywhere in `verdict_fold` itself.
RENAMED_FORM = {
    "fields": [
        {"id": "verdict", "kind": "decision", "note": "go | stop. ..."},
    ]
}
RENAMED_TABLE = {"outcome": [
    {"value": "go", "does": "release"},
    {"value": "stop", "does": "release"},
]}


def test_case_13_ranking_survives_renaming_the_verdict_words():
    returns = [_ret("w.step.p1", "go"), _ret("w.step.p2", "stop")]
    outcome = runmod.verdict_fold(returns, [RENAMED_FORM, RENAMED_FORM], RENAMED_TABLE)
    assert outcome == ("clean", "stop")

    returns_swapped = [_ret("w.step.p1", "stop"), _ret("w.step.p2", "go")]
    outcome2 = runmod.verdict_fold(returns_swapped, [RENAMED_FORM, RENAMED_FORM], RENAMED_TABLE)
    assert outcome2 == ("clean", "stop")
