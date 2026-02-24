"""Example tests for fd5."""


def test_example():
    """Example test that always passes."""
    assert True


def test_import():
    """Test that the package can be imported."""
    import fd5  # noqa: F401 - renamed to project name by init-workspace.sh

    assert fd5.__version__ == "0.1.0"
