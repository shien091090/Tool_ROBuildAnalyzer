import json
import os
from dataclasses import dataclass

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUADEC_EXE = os.path.join(_REPO_ROOT, "data", "tools", "luadec.exe")
UNLUAC_JAR = os.path.join(_REPO_ROOT, "data", "tools", "unluac.jar")


class ConfigNotFoundError(Exception):
    pass


class ConfigInvalidError(Exception):
    pass


@dataclass
class Config:
    dro_path: str
    java_exe: str
    db_path: str

    @property
    def data_grf_path(self) -> str:
        return os.path.join(self.dro_path, "data.grf")

    @property
    def iteminfo_lub_path(self) -> str:
        return os.path.join(self.dro_path, "System", "iteminfo_new.lub")


def load(path: str = "config.json") -> Config:
    if not os.path.exists(path):
        raise ConfigNotFoundError(
            f"找不到設定檔 {path}, 請複製 config.example.json 為 config.json 並填入DRO路徑"
        )
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if "dro_path" not in raw:
        raise ConfigInvalidError(
            f"config.json 缺少 dro_path 欄位, 請填入DRO遊戲資料夾路徑"
        )
    return Config(
        dro_path=raw["dro_path"],
        java_exe=raw.get("java_exe", "java"),
        db_path=raw.get("db_path", "data/ro_items.db"),
    )
