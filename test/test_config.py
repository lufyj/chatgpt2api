import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
ROOT_CONFIG_FILE = ROOT_DIR / "config.json"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class ConfigLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._created_root_config = False
        if not ROOT_CONFIG_FILE.exists():
            ROOT_CONFIG_FILE.write_text(json.dumps({"auth-key": "test-auth"}), encoding="utf-8")
            cls._created_root_config = True

        from services import config as config_module

        cls.config_module = config_module

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._created_root_config and ROOT_CONFIG_FILE.exists():
            ROOT_CONFIG_FILE.unlink()

    def _load_settings(
        self,
        *,
        config_payload: dict | None = None,
        env: dict[str, str] | None = None,
    ):
        module = self.config_module
        old_base_dir = module.BASE_DIR
        old_data_dir = module.DATA_DIR
        old_config_file = module.CONFIG_FILE
        env_keys = [
            "CHATGPT2API_AUTH_KEY",
            "CHATGPT2API_PROXY",
            "CHATGPT2API_HTTP_PROXY",
            "CHATGPT2API_HTTPS_PROXY",
        ]
        old_env = {key: module.os.environ.get(key) for key in env_keys}
        try:
            module.BASE_DIR = ROOT_DIR
            module.DATA_DIR = ROOT_DIR / "data"
            module.CONFIG_FILE = ROOT_DIR / "config.json"
            for key in env_keys:
                module.os.environ.pop(key, None)
            for key, value in (env or {}).items():
                module.os.environ[key] = value

            fake_path = module.CONFIG_FILE
            with patch.object(module, "_readable_json_file", return_value=fake_path if config_payload is not None else None):
                with patch.object(module, "_load_json_object", return_value=config_payload or {}):
                    return module._load_settings()
        finally:
            module.BASE_DIR = old_base_dir
            module.DATA_DIR = old_data_dir
            module.CONFIG_FILE = old_config_file
            for key, value in old_env.items():
                if value is None:
                    module.os.environ.pop(key, None)
                else:
                    module.os.environ[key] = value

    def test_load_settings_uses_environment_when_config_is_unavailable(self) -> None:
        settings = self._load_settings(
            env={"CHATGPT2API_AUTH_KEY": "env-auth"},
        )

        self.assertEqual(settings.auth_key, "env-auth")
        self.assertEqual(settings.refresh_account_interval_minute, 60)
        self.assertEqual(settings.session_kwargs(), {})

    def test_load_settings_reads_proxy_values_from_config_file(self) -> None:
        settings = self._load_settings(
            config_payload={
                "auth-key": "config-auth",
                "refresh_account_interval_minute": 5,
                "proxy": "socks5://127.0.0.1:7890",
                "http-proxy": "http://127.0.0.1:7891",
                "https-proxy": "http://127.0.0.1:7892",
            }
        )

        self.assertEqual(settings.auth_key, "config-auth")
        self.assertEqual(settings.refresh_account_interval_minute, 5)
        self.assertEqual(
            settings.session_kwargs(),
            {
                "proxies": {
                    "all": "socks5://127.0.0.1:7890",
                    "http": "http://127.0.0.1:7891",
                    "https": "http://127.0.0.1:7892",
                }
            },
        )

    def test_environment_proxy_values_override_config_file(self) -> None:
        settings = self._load_settings(
            config_payload={
                "auth-key": "config-auth",
                "proxy": "socks5://127.0.0.1:7890",
                "http-proxy": "http://127.0.0.1:7891",
                "https-proxy": "http://127.0.0.1:7892",
            },
            env={
                "CHATGPT2API_AUTH_KEY": "env-auth",
                "CHATGPT2API_PROXY": "socks5://127.0.0.1:8890",
                "CHATGPT2API_HTTP_PROXY": "http://127.0.0.1:8891",
                "CHATGPT2API_HTTPS_PROXY": "http://127.0.0.1:8892",
            },
        )

        self.assertEqual(settings.auth_key, "env-auth")
        self.assertEqual(settings.proxy, "socks5://127.0.0.1:8890")
        self.assertEqual(settings.http_proxy, "http://127.0.0.1:8891")
        self.assertEqual(settings.https_proxy, "http://127.0.0.1:8892")


if __name__ == "__main__":
    unittest.main()
