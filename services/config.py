from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config.json"


def _readable_json_file(path: Path, *, name: str) -> Path | None:
    if not path.exists():
        return None
    if path.is_dir():
        print(
            f"Warning: {name} at '{path}' is a directory, ignoring it and falling back to other configuration sources.",
            file=sys.stderr,
        )
        return None
    return path


def _load_json_object(path: Path, *, name: str) -> dict[str, object]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must be a JSON object")
    return loaded


def _optional_setting(value: object) -> str:
    return str(value or "").strip()


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        if not self.auth_key:
            raise ValueError(
                "❌ auth-key 未设置！\n"
                "请按以下任意一种方式解决：\n"
                "1. 在 Render 的 Environment 变量中添加：\n"
                "   CHATGPT2API_AUTH_KEY = your_real_auth_key\n"
                "2. 或者在 config.json 中填写：\n"
                '   "auth-key": "your_real_auth_key"'
            )

    def _load(self) -> dict[str, object]:
        config_file = _readable_json_file(self.path, name=self.path.name)
        if config_file is None:
            return {}
        try:
            return _load_json_object(config_file, name=config_file.name)
        except Exception:
            return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @property
    def auth_key(self) -> str:
        return _optional_setting(os.getenv("CHATGPT2API_AUTH_KEY") or self.data.get("auth-key"))

    @property
    def accounts_file(self) -> Path:
        return DATA_DIR / "accounts.json"

    @property
    def refresh_account_interval_minute(self) -> int:
        try:
            return int(self.data.get("refresh_account_interval_minute", 60))
        except (TypeError, ValueError):
            return 60

    def get(self) -> dict[str, object]:
        return dict(self.data)

    def get_proxy_settings(self) -> str:
        return (
            _optional_setting(os.getenv("CHATGPT2API_PROXY"))
            or _optional_setting(os.getenv("CHATGPT2API_HTTPS_PROXY"))
            or _optional_setting(os.getenv("CHATGPT2API_HTTP_PROXY"))
            or _optional_setting(self.data.get("proxy"))
            or _optional_setting(self.data.get("https-proxy") or self.data.get("https_proxy"))
            or _optional_setting(self.data.get("http-proxy") or self.data.get("http_proxy"))
        )

    def update(self, data: dict[str, object]) -> dict[str, object]:
        self.data = dict(data or {})
        self._save()
        return self.get()


def _load_settings() -> ConfigStore:
    return ConfigStore(CONFIG_FILE)


config = _load_settings()
