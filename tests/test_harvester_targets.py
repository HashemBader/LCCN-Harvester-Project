from unittest.mock import patch

from src.harvester.targets import Z3950Target


def test_gui_z3950_target_skips_lookup_when_pyz3950_is_unavailable():
    """The GUI target adapter should fail cleanly before constructing a client."""
    with patch("src.harvester.targets.ensure_pyz3950_importable", return_value=(False, "lexer build failed")), \
         patch("src.z3950.client.Z3950Client") as mock_cls:
        result = Z3950Target("Test", "z3950.test.org", 210, "testdb").lookup("0000000000")

    assert result.success is False
    assert "z39.50 support not available" in result.error.lower()
    mock_cls.assert_not_called()
