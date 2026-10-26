"""Bewerbung per E-Mail (SMTP) versenden – nur nach deiner Freigabe in Telegram."""

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid


def sende(cfg, an, betreff, text, anhaenge=()):
    """cfg: dict mit host, port, benutzer, passwort, absender, absender_name."""
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.get("absender_name") or "", cfg["absender"]))
    msg["To"] = an
    msg["Subject"] = betreff
    msg["Reply-To"] = cfg["absender"]
    msg["Message-ID"] = make_msgid(domain=cfg["absender"].split("@")[-1])
    msg.set_content(text)
    for dateiname, daten in anhaenge:
        typ = mimetypes.guess_type(dateiname)[0] or "application/octet-stream"
        haupt, unter = typ.split("/", 1)
        msg.add_attachment(daten, maintype=haupt, subtype=unter, filename=dateiname)

    port = int(cfg.get("port") or 587)
    kontext = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(cfg["host"], port, context=kontext, timeout=60)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=60)
    with server:
        if port != 465 and cfg.get("starttls", True):
            server.starttls(context=kontext)
        if cfg.get("benutzer"):
            server.login(cfg["benutzer"], cfg["passwort"])
        server.send_message(msg)
    return msg
