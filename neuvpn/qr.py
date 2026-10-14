"""QR code output for importing client configs into the WireGuard mobile apps."""

import shutil
import subprocess


def terminal_qr(text: str) -> str | None:
    """Render `text` as a terminal QR code, or return None if no renderer exists."""
    if shutil.which("qrencode"):
        result = subprocess.run(
            ["qrencode", "-t", "ansiutf8", "-l", "L"],
            input=text.encode(),
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.decode()
    try:
        import qrcode  # optional: pip install qrcode
    except ImportError:
        return None
    import io

    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    buf = io.StringIO()
    qr.print_ascii(out=buf, invert=True)
    return buf.getvalue()


def png_qr(text: str, path: str) -> bool:
    if not shutil.which("qrencode"):
        return False
    result = subprocess.run(["qrencode", "-t", "png", "-o", path], input=text.encode(), check=False)
    return result.returncode == 0
