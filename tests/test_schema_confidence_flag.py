from generator.schema import ConfidenceFlag


def test_confidence_flag_has_exactly_three_values():
    import typing
    args = set(typing.get_args(ConfidenceFlag))
    assert args == {"single_source", "low_tier_only", "contested_fact"}
