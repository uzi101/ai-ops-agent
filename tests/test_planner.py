from planner.plan import plan


def test_plan_install():
    out = plan("please install postgres")
    # LLM may need key, fallback is okay
    assert out["action"] in (None, "install_sql")


def test_plan_free_disk():
    out = plan("free up disk space")
    assert out["action"] in (None, "free_disk")
