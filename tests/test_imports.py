def test_import_without_scripts():
    # Ensure top-level package imports without running generation scripts
    import ltba  # noqa: F401

    assert hasattr(ltba, "LTBAExpr") or hasattr(ltba, "registry")
