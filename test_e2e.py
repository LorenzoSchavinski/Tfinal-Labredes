"""
Teste de integração ponta a ponta (sockets reais em localhost).

Roda o receiver numa thread e o sender na thread principal, transferindo um
arquivo e conferindo que o hash do recebido bate com o original.
"""
import hashlib
import os
import tempfile
import threading
import unittest

from receiver import run_receiver
from sender import run_sender


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


class TestEndToEnd(unittest.TestCase):
    def _transfer(self, size, port):
        d = tempfile.mkdtemp()
        infile = os.path.join(d, "in.bin")
        outfile = os.path.join(d, "out.bin")
        # conteúdo determinístico (sem Math.random): bytes 0..255 repetidos
        with open(infile, "wb") as f:
            f.write(bytes(i % 256 for i in range(size)))

        rx = threading.Thread(
            target=run_receiver, args=(port,),
            kwargs={"outpath": outfile}, daemon=True)
        rx.start()
        run_sender("127.0.0.1", port, infile)
        rx.join(timeout=15)
        self.assertFalse(rx.is_alive(), "receiver não encerrou")
        self.assertEqual(sha256(infile), sha256(outfile),
                         f"hash diferente para tamanho {size}")

    def test_arquivo_grande_ultimo_pacote_parcial(self):
        # 15123 bytes -> 60 pacotes, último com 78 bytes (>50 pacotes)
        self._transfer(15123, 7000)

    def test_multiplo_exato_de_255(self):
        # 255*60 -> precisa do pacote terminador Length=0
        self._transfer(255 * 60, 7002)

    def test_arquivo_pequeno_um_pacote(self):
        self._transfer(100, 7004)

    def test_arquivo_vazio(self):
        self._transfer(0, 7006)


if __name__ == "__main__":
    unittest.main()
