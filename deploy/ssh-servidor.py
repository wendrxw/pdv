#!/usr/bin/env python
"""Executa comandos no servidor de produção via SSH (uso padrão do agente).

Credenciais: lidas de deploy/servidor.ssh.env (git-ignored) ou das
variáveis de ambiente PDV_SERVER_HOST/USER/PASSWORD/SUDO_PASSWORD.

Dependência: paramiko. Execute com:
  uv run --with paramiko --no-project deploy/ssh-servidor.py "<comando>"
ou, se já houver venv com paramiko:
  python deploy/ssh-servidor.py "<comando>"

Opções:
  --sudo      executa com sudo (senha informada via env)
  --timeout N tempo limite (padrão 120s)
  --upload <arquivo> <destino>  copia um arquivo para o servidor (via sudo)
"""

import base64
import os
import sys

import paramiko

ENV = os.environ

# deploy/servidor.ssh.env (não versionado) tem prioridade sobre o ambiente.
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor.ssh.env")


def _carregar_env_file():
    if not os.path.exists(_ENV_FILE):
        return
    with open(_ENV_FILE, encoding="utf-8") as handle:
        for linha in handle:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env_file()

HOST = ENV.get("PDV_SERVER_HOST", "192.168.1.119")
USER = ENV.get("PDV_SERVER_USER", "servidor1")
PASSWORD = ENV.get("PDV_SERVER_PASSWORD", "")
SUDO_PASSWORD = ENV.get("PDV_SERVER_SUDO_PASSWORD", PASSWORD)


def _conectar():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        username=USER,
        password=PASSWORD,
        timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


def _exec(client, comando, timeout):
    _stdin, stdout, stderr = client.exec_command(comando, timeout=timeout)
    saida = stdout.read().decode("utf-8", "replace")
    erros = stderr.read().decode("utf-8", "replace")
    codigo = stdout.channel.recv_exit_status()
    return saida, erros, codigo


def main():
    args = sys.argv[1:]
    if "--upload" in args:
        idx = args.index("--upload")
        local, destino = args[idx + 1], args[idx + 2]
        client = _conectar()
        sftp = client.open_sftp()
        sftp.put(local, "/tmp/upload-pdv")
        sftp.close()
        comando = (
            f"echo '{SUDO_PASSWORD}' | sudo -S -p '' sh -c "
            f"'install -m 0644 /tmp/upload-pdv {destino} && rm -f /tmp/upload-pdv'"
        )
        saida, erros, codigo = _exec(client, comando, 120)
        print(saida, end="")
        if erros.strip():
            print("--- STDERR ---\n" + erros)
        print(f"EXIT={codigo}")
        client.close()
        return

    use_sudo = "--sudo" in args
    timeout = 120
    if "--timeout" in args:
        timeout = int(args[args.index("--timeout") + 1])
    args = [a for a in args if a not in ("--sudo", "--timeout")]
    if "--timeout" in sys.argv:
        pass
    comando = " ".join(args)

    client = _conectar()
    if use_sudo:
        encoded = base64.b64encode(comando.encode()).decode()
        comando = (
            f"echo '{SUDO_PASSWORD}' | sudo -S -p '' sh -c "
            f'"echo {encoded} | base64 -d | sh"'
        )
    saida, erros, codigo = _exec(client, comando, timeout)
    print(saida, end="")
    if erros.strip():
        print("--- STDERR ---\n" + erros)
    print(f"EXIT={codigo}")
    client.close()


if __name__ == "__main__":
    main()
