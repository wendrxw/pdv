"""Testes da configuração local persistente e do autostart no Windows."""

import sys
import tempfile
import types
import unittest
from pathlib import Path

from app.config import Config


class ConfigLocalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = Config(
            server_url="http://padrao:8000",
            device="",
            label_device="",
            state_dir=self.tmp,
        )

    def test_salvar_e_carregar_local(self):
        self.config.server_url = "https://pdv.wendrxw.online"
        self.config.device = "Elgin L42 PRO"
        self.config.label_device = "Térmica 58"
        self.config.salvar_local()
        nova = Config(server_url="http://padrao:8000", state_dir=self.tmp)
        nova = Config.carregar_local(nova)
        self.assertEqual(nova.server_url, "https://pdv.wendrxw.online")
        self.assertEqual(nova.device, "Elgin L42 PRO")
        self.assertEqual(nova.label_device, "Térmica 58")

    def test_local_nao_sobrescreve_com_vazio(self):
        self.config.device = "Elgin"
        self.config.salvar_local()
        nova = Config(server_url="http://x", state_dir=self.tmp)
        nova = Config.carregar_local(nova)
        self.assertEqual(nova.device, "Elgin")

    def test_sem_arquivo_local_mantem_config(self):
        nova = Config.carregar_local(self.config)
        self.assertEqual(nova.device, "")


class AutostartWindowsTest(unittest.TestCase):
    """Autostart no HKCU com winreg fake (não existe no Linux)."""

    def _injetar_winreg(self, valores):
        fake = types.ModuleType("winreg")
        fake.HKEY_CURRENT_USER = "HKCU"
        fake.REG_SZ = 1

        def create_key(hive, caminho):
            return valores

        def set_value_ex(chave, nome, _reservado, tipo, valor):
            chave[nome] = valor

        def delete_value(chave, nome):
            chave.pop(nome, None)

        def close_key(chave):
            pass

        fake.CreateKey = create_key
        fake.SetValueEx = set_value_ex
        fake.DeleteValue = delete_value
        fake.CloseKey = close_key
        sys.modules["winreg"] = fake
        return valores

    def tearDown(self):
        sys.modules.pop("winreg", None)

    def test_instalar_autostart_grava_comando(self):
        valores = {}
        self._injetar_winreg(valores)
        with unittest.mock.patch("sys.platform", "win32"):
            from app.main import comando_instalar_autostart

            comando_instalar_autostart(Config(server_url="http://x"))
        self.assertIn("PDV-Print-Agent", valores)
        self.assertIn("app.main run", valores["PDV-Print-Agent"])

    def test_remover_autostart(self):
        valores = {"PDV-Print-Agent": "algo"}
        self._injetar_winreg(valores)
        with unittest.mock.patch("sys.platform", "win32"):
            from app.main import comando_remover_autostart

            comando_remover_autostart(Config(server_url="http://x"))
        self.assertNotIn("PDV-Print-Agent", valores)

    def test_autostart_no_linux_avisa(self):
        self._injetar_winreg({})
        from app.main import comando_instalar_autostart

        with self.assertRaises(SystemExit):
            comando_instalar_autostart(Config(server_url="http://x"))


if __name__ == "__main__":
    unittest.main()
