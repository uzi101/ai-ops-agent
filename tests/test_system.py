from runbooks.system import free_disk, check_cpu_mem


def test_free_disk_dryrun():
    res = free_disk(dry_run=True)
    assert res["ok"] is True
    assert isinstance(res["actions"], list)


def test_check_cpu_mem_dryrun():
    res = check_cpu_mem(dry_run=True)
    assert res["ok"] is True
    assert isinstance(res["checks"], list)
    assert len(res["checks"]) >= 2
