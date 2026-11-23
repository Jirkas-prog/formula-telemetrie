"""Set the share password and publish it to authenticated Formula Manager clients."""
import getpass
import grp
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    if os.geteuid() != 0:
        raise SystemExit("Spusť pomocí sudo.")
    password = getpass.getpass("Heslo Samby pro formula69: ")
    if not password or getpass.getpass("Zopakuj heslo: ") != password:
        raise SystemExit("Hesla se neshodují nebo jsou prázdná.")
    dest = Path("/etc/formula-manager/samba-password")
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        name = Path(tmp.name)
        try:
            tmp.write(password.encode("utf-8") + b"\n")
            tmp.flush()
            os.fsync(tmp.fileno())
            os.fchown(tmp.fileno(), 0, grp.getgrnam("formula-manager").gr_gid)
            os.fchmod(tmp.fileno(), 0o640)
            subprocess.run(["smbpasswd", "-s", "-a", "formula69"],
                           input=(password+"\n")*2, encoding="utf-8", check=True)
            os.replace(name, dest)
        finally:
            name.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

