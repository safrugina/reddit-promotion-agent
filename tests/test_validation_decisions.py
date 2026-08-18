from app.db.models.enums import ValidationStatus
from app.validation.duplication import normalized_text_similarity
from app.validation.service import determine_validation_status


def test_identical_text_has_similarity_one():
    assert normalized_text_similarity("Hello world", "hello   world") == 1.0


def test_different_text_has_low_similarity():
    assert normalized_text_similarity("Postgres migrations tool", "Cooking recipes blog") < 0.5


def test_status_blocks_on_explicit_rule_violation():
    status = determine_validation_status(
        rule_status="BLOCK", grounding=100, promotion=0, originality=100
    )
    assert status == ValidationStatus.BLOCK


def test_status_regenerates_on_low_grounding():
    status = determine_validation_status(
        rule_status="PASS", grounding=20, promotion=0, originality=100
    )
    assert status == ValidationStatus.REGENERATE


def test_status_regenerates_on_high_promotion_risk():
    status = determine_validation_status(
        rule_status="PASS", grounding=100, promotion=85, originality=100
    )
    assert status == ValidationStatus.REGENERATE


def test_status_regenerates_on_near_duplicate():
    status = determine_validation_status(
        rule_status="PASS", grounding=100, promotion=0, originality=10
    )
    assert status == ValidationStatus.REGENERATE


def test_status_passes_when_all_checks_clean():
    status = determine_validation_status(
        rule_status="PASS", grounding=90, promotion=10, originality=80
    )
    assert status == ValidationStatus.PASS


def test_block_takes_priority_over_other_failures():
    status = determine_validation_status(
        rule_status="BLOCK", grounding=0, promotion=100, originality=0
    )
    assert status == ValidationStatus.BLOCK
