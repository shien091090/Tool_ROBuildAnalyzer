import subprocess


def run_luadec(luadec_exe: str, lub_path: str, out_path: str) -> None:
    with open(out_path, "wb") as out_file:
        subprocess.run([luadec_exe, lub_path], stdout=out_file, stderr=subprocess.PIPE, check=True)


def run_unluac(java_exe: str, unluac_jar: str, lub_path: str, out_path: str) -> None:
    with open(out_path, "wb") as out_file:
        subprocess.run(
            [java_exe, "-jar", unluac_jar, lub_path],
            stdout=out_file, stderr=subprocess.PIPE, check=True,
        )
