from importer import decompile


def test_run_luadec_builds_correct_command(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, stdout, stderr, check):
        captured["cmd"] = cmd
        stdout.write(b"-- decompiled\n")
        return None

    monkeypatch.setattr(decompile.subprocess, "run", fake_run)

    out_path = tmp_path / "out.lua"
    decompile.run_luadec("C:/tools/luadec.exe", "C:/lub/x.lub", str(out_path))

    assert captured["cmd"] == ["C:/tools/luadec.exe", "C:/lub/x.lub"]
    assert out_path.read_bytes() == b"-- decompiled\n"


def test_run_unluac_builds_correct_command(tmp_path, monkeypatch):
    captured = {}

    def fake_run(cmd, stdout, stderr, check):
        captured["cmd"] = cmd
        stdout.write(b"-- decompiled by unluac\n")
        return None

    monkeypatch.setattr(decompile.subprocess, "run", fake_run)

    out_path = tmp_path / "out.lua"
    decompile.run_unluac("C:/jre/java.exe", "C:/tools/unluac.jar", "C:/lub/x.lub", str(out_path))

    assert captured["cmd"] == ["C:/jre/java.exe", "-jar", "C:/tools/unluac.jar", "C:/lub/x.lub"]
    assert out_path.read_bytes() == b"-- decompiled by unluac\n"
