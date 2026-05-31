# src/utils/telegram.py
"""Telegram notification sender with chunked message support."""

import logging
import os
import time
from typing import List, Optional

import requests

logger = logging.getLogger('portfolio_analyzer.telegram')

_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_MAX_CHUNK = 3500  # Telegram limit is 4096; stay well under


class TelegramSender:
    """
    Send messages to a Telegram chat, splitting long messages into chunks.

    Args:
        token: Telegram bot token (from @BotFather).
        chat_id: Destination chat/channel ID.
        max_retries: Retry attempts per chunk on network failure.
    """

    def __init__(self, token: str, chat_id: str, max_retries: int = 3):
        self.token = token
        self.chat_id = str(chat_id)
        self.max_retries = max_retries

    def send(self, text: str, parse_mode: str = 'Markdown') -> bool:
        """Send text, chunking at _MAX_CHUNK chars. Returns True if all chunks sent."""
        ok = True
        for chunk in _chunk(text, _MAX_CHUNK):
            ok = self._send_one(chunk, parse_mode) and ok
        return ok

    def send_error(self, script_name: str, error: str) -> bool:
        """Send a formatted error alert."""
        snippet = str(error)[:600]
        msg = f"❌ *{script_name}* failed\n```\n{snippet}\n```"
        # Fall back to plain text if Markdown parse fails
        return self._send_one(msg, 'Markdown') or self._send_one(
            f"ERROR in {script_name}: {snippet}", 'MarkdownV2'
        )

    def _send_one(self, text: str, parse_mode: str) -> bool:
        url = _API_BASE.format(token=self.token, method='sendMessage')
        payload = {'chat_id': self.chat_id, 'text': text, 'parse_mode': parse_mode}
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(url, json=payload, timeout=15)
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"Telegram send attempt {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
        return False


def from_env() -> Optional[TelegramSender]:
    """Build a TelegramSender from TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env vars.

    Returns None (silently) if either var is absent — callers treat Telegram as optional.
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if token and chat_id:
        return TelegramSender(token, chat_id)
    logger.debug("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — Telegram disabled")
    return None


def _chunk(text: str, size: int) -> List[str]:
    """Split text into chunks of at most `size` chars, breaking on newlines where possible."""
    if len(text) <= size:
        return [text]
    chunks: List[str] = []
    current_lines: List[str] = []
    current_len = 0
    for line in text.split('\n'):
        line_len = len(line) + 1  # +1 for the newline
        if current_len + line_len > size and current_lines:
            chunks.append('\n'.join(current_lines))
            current_lines = [line]
            current_len = line_len
        else:
            current_lines.append(line)
            current_len += line_len
    if current_lines:
        chunks.append('\n'.join(current_lines))
    return chunks
