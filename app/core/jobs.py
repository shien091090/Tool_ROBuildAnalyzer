"""職業血統表 — 移植自ROItemSearchApp data/job_dict.py(GPL-3.0)的GetPureJob清單,
中文血統關鍵字依DRO client道具「裝備 : 」欄位實際用詞(見spec §9.1)。
注意: job_dict原文4262(聖裁者)血統列4006(商人High), 依RO job id表應為4005(服事High),
此處採4005; 4307(終極初學者)job_dict已收錄GetPureJob=[0,23,4001,4190,4307],與RO通用
id補法一致,故直接沿用原檔清單。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class JobInfo:
    job_id: int
    name: str
    pure_jobs: tuple[int, ...]
    keywords: tuple[str, ...]


_JOBS = (
    JobInfo(4252, "盧恩龍爵", (1, 7, 4002, 4008, 4054, 4060, 4252), ("劍士", "騎士", "盧恩騎士", "盧恩龍爵")),
    JobInfo(4253, "機甲神匠", (5, 10, 4006, 4011, 4058, 4064, 4253), ("商人", "鐵匠", "機械工匠", "機甲神匠")),
    JobInfo(4254, "十字影武", (6, 12, 4007, 4013, 4059, 4065, 4254), ("盜賊", "刺客", "十字斬首者", "十字影武")),
    JobInfo(4255, "禁咒魔導士", (2, 9, 4003, 4010, 4055, 4061, 4255), ("魔法師", "巫師", "咒術士", "禁咒魔導士")),
    JobInfo(4256, "樞機主教", (4, 8, 4005, 4009, 4057, 4063, 4256), ("服事", "牧師", "祭司", "大主教", "樞機主教")),
    JobInfo(4257, "風鷹狩獵者", (3, 11, 4004, 4012, 4056, 4062, 4257), ("弓箭手", "獵人", "遊俠", "風鷹狩獵者")),
    JobInfo(4258, "帝國聖衛軍", (1, 14, 4002, 4015, 4066, 4073, 4258), ("劍士", "十字軍", "皇家禁衛隊", "帝國聖衛軍")),
    JobInfo(4259, "生命締造者", (5, 18, 4006, 4019, 4071, 4078, 4259), ("商人", "煉金術師", "基因學者", "生命締造者")),
    JobInfo(4260, "深淵追跡者", (6, 12, 4007, 4018, 4072, 4079, 4260), ("盜賊", "流氓", "魅影追蹤者", "深淵追跡者")),
    JobInfo(4261, "元素支配者", (2, 16, 4003, 4017, 4067, 4074, 4261), ("魔法師", "賢者", "妖術師", "元素支配者")),
    JobInfo(4262, "聖裁者", (4, 15, 4005, 4016, 4070, 4077, 4262), ("服事", "武道家", "武僧", "修羅", "聖裁者")),
    JobInfo(4263, "天籟頌者", (3, 19, 4004, 4020, 4068, 4075, 4263), ("弓箭手", "吟遊詩人", "宮廷樂師", "天籟頌者")),
    JobInfo(4264, "樂之舞靈", (3, 20, 4004, 4021, 4069, 4076, 4264), ("弓箭手", "舞孃", "浪姬舞者", "樂之舞靈")),
    JobInfo(4302, "天帝", (4046, 4047, 4239, 4302), ("太極拳士", "拳聖", "天帝")),
    JobInfo(4303, "契靈士", (4046, 4049, 4240, 4303), ("太極拳士", "悟靈士", "契靈士")),
    JobInfo(4304, "流浪忍者", (25, 4211, 4304), ("忍者", "影狼", "流浪忍者")),
    JobInfo(4305, "疾風忍者", (25, 4212, 4305), ("忍者", "朧", "疾風忍者")),
    JobInfo(4306, "夜行者", (24, 4215, 4306), ("神槍手", "叛亂者", "夜行者", "夜行使")),
    JobInfo(4307, "終極初學者", (0, 23, 4001, 4190, 4307), ("初學者", "超級初學者", "終極初學者")),
    JobInfo(4308, "魂靈師", (4218, 4308), ("喵族", "召喚師", "魂靈師")),
)

JOB_TABLE: dict[int, JobInfo] = {j.job_id: j for j in _JOBS}
_ALL_KEYWORDS = frozenset(k for j in _JOBS for k in j.keywords)
_UNIVERSAL = ("全職業", "所有職業", "初學者以外", "除了初學者", "進階職業")
_NOVICE_EXCLUSION = ("初學者以外", "除了初學者")
_NOVICE_JOBS = frozenset({4307})


def pure_jobs_for(job_id: int) -> list[int]:
    info = JOB_TABLE.get(job_id)
    return list(info.pure_jobs) if info else [job_id]


def job_name(job_id: int) -> str:
    info = JOB_TABLE.get(job_id)
    return info.name if info else f"職業{job_id}"


def is_equippable_by(job_id: int, equip_text: str | None) -> bool:
    """依道具「裝備 : 」文字判斷job_id可否裝備。無資訊/表外職業/非職業描述一律不擋(寧可多列不可漏列)。"""
    if not equip_text or not equip_text.strip():
        return True
    info = JOB_TABLE.get(job_id)
    if info is None:
        return True
    text = equip_text
    if job_id in _NOVICE_JOBS and any(p in text for p in _NOVICE_EXCLUSION):
        return False
    if any(k in text for k in info.keywords):
        return True
    if any(p in text for p in _UNIVERSAL):
        return True
    if any(k in text for k in _ALL_KEYWORDS):
        return False
    return True
