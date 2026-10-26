"""Minimaler Telegram-Bot-API-Client (nur requests, keine Zusatzbibliothek)."""

import html

import requests


class TelegramFehler(Exception):
    pass


def h(text):
    """Text für parse_mode=HTML entschärfen."""
    return html.escape(str(text or ""), quote=False)


def knoepfe(*reihen):
    """knoepfe([("Text", "daten"), ...], ...) -> reply_markup"""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in reihe] for reihe in reihen if reihe]}


class Telegram:
    def __init__(self, token, api="https://api.telegram.org"):
        self.basis = f"{api.rstrip('/')}/bot{token}"
        self.session = requests.Session()

    def _rufe(self, methode, http_timeout=30, **params):
        params = {k: v for k, v in params.items() if v is not None}
        try:
            r = self.session.post(f"{self.basis}/{methode}", json=params, timeout=http_timeout)
            daten = r.json()
        except (requests.RequestException, ValueError) as e:
            raise TelegramFehler(f"{methode}: {e.__class__.__name__}") from None
        if not daten.get("ok"):
            raise TelegramFehler(f"{methode}: {daten.get('description', r.status_code)}")
        return daten["result"]

    def sende(self, chat_id, text, markup=None, antwort_auf=None):
        if len(text) > 4000:
            text = text[:3990] + "\n…"
        return self._rufe("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                          reply_markup=markup, disable_web_page_preview=True,
                          reply_to_message_id=antwort_auf)

    def knoepfe_aendern(self, chat_id, nachricht_id, markup=None):
        try:
            self._rufe("editMessageReplyMarkup", chat_id=chat_id, message_id=nachricht_id,
                       reply_markup=markup or {"inline_keyboard": []})
        except TelegramFehler:
            pass  # z. B. Nachricht zu alt oder unverändert – nicht schlimm

    def callback_beantworten(self, callback_id, text=None):
        try:
            self._rufe("answerCallbackQuery", callback_query_id=callback_id, text=text)
        except TelegramFehler:
            pass

    def updates(self, offset=None, timeout=25):
        """Long-Polling: wartet bis zu `timeout` Sekunden auf Knopfdrücke/Nachrichten."""
        return self._rufe("getUpdates", http_timeout=timeout + 10, offset=offset, timeout=timeout,
                          allowed_updates=["message", "callback_query"])
