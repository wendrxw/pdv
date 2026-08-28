"""Testes de bootstrap: importação, versão, Config e entry point."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pdv_desktop import __version__
from pdv_desktop.config import SERVIDOR_PADRAO, Config, carregar, salvar
from pdv_desktop.main import main, montar_parser


class BootstrapTest(unittest.TestCase):
    def test_pacote_importavel_com_versao(self):
        self.assertEqual(__version__, "0.1.0")

    def test_parser_tem_version(self):
        with self.assertRaises(SystemExit) as ctx:
            montar_parser().parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_main_retorna_zero(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "pdv_desktop.main.DIR_ESTADO", Path(tmp)
        ):
            self.assertEqual(main([]), 0)


class ConfigTest(unittest.TestCase):
    def test_padrao_aponta_para_producao(self):
        config = Config()
        self.assertEqual(config.server_url, SERVIDOR_PADRAO)
        self.assertTrue(config.janela_largura > config.janela_min_largura)
        self.assertFalse(config.lembrar_sessao)

    def test_carregar_sem_arquivo_usa_padrao(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "inexistente.json"
            config = carregar(caminho)
        self.assertEqual(config.server_url, SERVIDOR_PADRAO)

    def test_salvar_e_carregar_roundtrip(self):
        config = Config(server_url="http://192.168.1.50:8000", lembrar_sessao=True)
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            salvar(config, caminho)
            lido = carregar(caminho)
            self.assertEqual(lido.server_url, "http://192.168.1.50:8000")
            self.assertTrue(lido.lembrar_sessao)
            conteudo = json.loads(caminho.read_text("utf-8"))
            self.assertEqual(conteudo["server_url"], config.server_url)

    def test_arquivo_de_config_tem_permissao_600(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            salvar(Config(), caminho)
            permissao = caminho.stat().st_mode & 0o777
            self.assertEqual(permissao, 0o600)

    def test_variavel_de_ambiente_sobrepoe_arquivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            salvar(Config(server_url="http://do-arquivo"), caminho)
            with mock.patch.dict(
                "os.environ",
                {"PDV_DESKTOP_SERVER_URL": "http://do-ambiente"},
            ):
                config = carregar(caminho)
            self.assertEqual(config.server_url, "http://do-ambiente")

    def test_env_booleano_aceita_sim(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"PDV_DESKTOP_LEMBRAR_SESSAO": "sim"}):
                config = carregar(Path(tmp) / "n.json")
            self.assertTrue(config.lembrar_sessao)
