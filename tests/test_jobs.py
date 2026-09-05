from app.core import jobs


def test_table_has_20_jobs_and_rk_lineage():
    assert len(jobs.JOB_TABLE) == 20
    assert jobs.pure_jobs_for(4252) == [1, 7, 4002, 4008, 4054, 4060, 4252]
    assert jobs.job_name(4252) == "盧恩龍爵"


def test_unknown_job_falls_back():
    assert jobs.pure_jobs_for(9999) == [9999]
    assert jobs.job_name(9999) == "職業9999"


def test_every_job_pure_list_contains_itself():
    for job_id, info in jobs.JOB_TABLE.items():
        assert job_id in info.pure_jobs
        assert info.keywords


def test_equippable_universal_and_lineage():
    assert jobs.is_equippable_by(4252, "全職業")
    assert jobs.is_equippable_by(4252, "初學者以外的全職業")
    assert jobs.is_equippable_by(4252, "盧恩騎士系列")
    assert jobs.is_equippable_by(4252, "劍士系列/商人系列")
    assert not jobs.is_equippable_by(4252, "魅影追蹤者系列")
    assert not jobs.is_equippable_by(4252, "喵族")


def test_equippable_novice_exclusion():
    assert not jobs.is_equippable_by(4307, "初學者以外的全職業")
    assert not jobs.is_equippable_by(4307, "除了初學者之外,全職業")
    assert jobs.is_equippable_by(4307, "全職業")
    assert jobs.is_equippable_by(4307, "終極初學者")


def test_equippable_non_job_text_and_unknown_job_not_blocked():
    assert jobs.is_equippable_by(4252, None)
    assert jobs.is_equippable_by(4252, "")
    assert jobs.is_equippable_by(4252, "鎧甲")            # 卡片的「裝備 : 鎧甲」不是職業描述
    assert jobs.is_equippable_by(9999, "魅影追蹤者系列")  # 表外職業不過濾
