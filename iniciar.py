"""
Ponto de entrada do .exe.

O .exe traz o "motor" (Python, OpenCV, leitor de fichas e modelos de IA), que
quase nunca muda. O codigo do programa (reconhecimento.py) pode ser
atualizado sozinho: o proprio programa baixa a versao nova para a pasta
"atualizacao" e, na proxima vez que abrir, este arquivo usa a mais nova.
Se a versao baixada der erro, volta para a que veio dentro do .exe.
"""

import importlib.util
import os
import re
import sys

# Versao do motor. So muda quando o .exe precisa ser baixado de novo
# (biblioteca nova, modelo novo...). O codigo novo diz qual motor precisa.
RUNTIME = 1

import reconhecimento as embutido  # noqa: E402  (tambem faz o PyInstaller incluir tudo)


def update_dir():
    return os.path.join(os.path.dirname(embutido.data_dir()), "atualizacao")


def file_version(path):
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r"^VERSAO\s*=\s*(\d+)", f.read(), re.M)
        return int(m.group(1)) if m else 0
    except OSError:
        return 0


def load_updated():
    """Carrega o codigo baixado se for mais novo que o embutido e servir neste motor."""
    path = os.path.join(update_dir(), "reconhecimento.py")
    if file_version(path) <= embutido.VERSAO:
        return None
    try:
        spec = importlib.util.spec_from_file_location("reconhecimento", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["reconhecimento"] = mod
        spec.loader.exec_module(mod)
        if getattr(mod, "RUNTIME_NEEDED", 1) > RUNTIME:
            raise RuntimeError("precisa de motor mais novo")
        return mod
    except Exception:
        sys.modules["reconhecimento"] = embutido
        discard(path)
        return None


def discard(path):
    try:
        os.replace(path, path + ".com_erro")
    except OSError:
        pass


def main():
    os.environ["RF_RUNTIME"] = str(RUNTIME)
    os.environ["RF_APP_DIR"] = embutido.app_dir()
    mod = load_updated()
    if mod is None:
        embutido.main(sys.argv[1:])
        return
    try:
        mod.main(sys.argv[1:])
    except SystemExit:
        raise
    except Exception:
        # a atualizacao quebrou algo: descarta e abre a versao do .exe
        discard(os.path.join(update_dir(), "reconhecimento.py"))
        sys.modules["reconhecimento"] = embutido
        embutido.main(sys.argv[1:])


if __name__ == "__main__":
    main()
