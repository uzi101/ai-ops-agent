from planner.plan import plan_actions


def _names(q, mode="auto"): return [s.name for s in plan_actions(q, mode=mode)]


def test_maps_free_disk_and_check_snapshot_rules():
    assert _names(
        "free disk and check cpu/mem") == ["free_disk", "check_cpu_mem"]


def test_maps_service_down_heal_rules():
    assert _names("web server crashed, restart and verify") == [
        "heal_fakesvc_8080"]


def test_auto_fallback_safe_default():
    out = _names("nonsense phrase")
    assert len(out) >= 1


def test_llm_mode_when_unconfigured_falls_back_safely():
    out = _names("novel request", mode="llm")
    assert len(out) >= 1
