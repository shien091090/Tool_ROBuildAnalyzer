# importer/cli.py
import os

from importer import config, decompile, fingerprint, grf, pipeline

_GRF_LUB_TARGETS = {
    "equipment_properties":
        "data\\luafiles514\\lua files\\equipmentproperties\\equipmentproperties.lub",
    "enchant": "data\\luafiles514\\lua files\\enchant\\enchantlist.lub",
    "itemdbname": "data\\luafiles514\\lua files\\itemdbnametbl.lub",
}
# 反編譯器選用比照SNShienRODataBase驗證過的組合:
# equipment_properties用unluac(luadec對這支會產出壞結構), 其餘用luadec
_UNLUAC_KEYS = {"equipment_properties"}


def main() -> None:
    cfg = config.load()
    os.makedirs("data/lub", exist_ok=True)
    os.makedirs("data/lua", exist_ok=True)
    os.makedirs(os.path.dirname(cfg.db_path) or ".", exist_ok=True)

    print("讀取GRF索引…")
    index = grf.build_index(cfg.data_grf_path)

    lub_paths = {}
    for key, rel in _GRF_LUB_TARGETS.items():
        entry = index[rel]
        lub_path = f"data/lub/{key}.lub"
        with open(lub_path, "wb") as f:
            f.write(grf.extract(cfg.data_grf_path, entry))
        lub_paths[key] = lub_path

    # iteminfo不在GRF裡, 直接拿System資料夾的檔案
    lub_paths["iteminfo"] = cfg.iteminfo_lub_path

    lua_texts = {}
    for key, lub_path in lub_paths.items():
        out_path = f"data/lua/{key}.lua"
        print(f"反編譯 {key}…")
        if key in _UNLUAC_KEYS:
            decompile.run_unluac(cfg.java_exe, config.UNLUAC_JAR, lub_path, out_path)
        else:
            decompile.run_luadec(config.LUADEC_EXE, lub_path, out_path)
        with open(out_path, encoding="utf-8", errors="replace") as f:
            lua_texts[key] = f.read()

    print("解析並寫入資料庫…")
    report = pipeline.run(
        lua_texts, cfg.db_path, fingerprint.of_file(cfg.data_grf_path))
    for k, v in report.items():
        print(f"{k}={v}")


if __name__ == "__main__":
    main()
