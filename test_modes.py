"""
Testes de integração dos três modos (saw / gbn / sr) com janela deslizante.

Usa um proxy UDP entre sender e receiver capaz de:
  - descartar pacotes de dados / ACKs (cenários de perda P1–P4),
  - reordenar pacotes de dados (cenários de reordenação R1–R2).

Em todos os casos a asserção principal é: o arquivo recebido é idêntico ao
original (hash SHA-256). Cobre GBN e SR com janelas 4 e 16.
"""
import hashlib
import os
import socket
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


class ImpairProxy(threading.Thread):
    """Encaminha entre sender e receiver, podendo perder e reordenar dados."""

    def __init__(self, listen_port, receiver_port,
                 drop_data_every=0, drop_ack_every=0, reorder_data_every=0):
        super().__init__(daemon=True)
        self.listen_port = listen_port                        # X (sender envia aqui)
        self.sender_addr = ("127.0.0.1", listen_port + 1)     # X+1 (ACKs vão pra cá)
        self.receiver_addr = ("127.0.0.1", receiver_port)     # Y
        self.drop_data_every = drop_data_every
        self.drop_ack_every = drop_ack_every
        self.reorder_data_every = reorder_data_every
        self._stop_evt = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", listen_port))
        self.sock.settimeout(0.2)

    def run(self):
        data_count = 0
        ack_count = 0
        pending = None  # pacote de dados segurado para reordenar
        while not self._stop_evt.is_set():
            try:
                pkt, src = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue  # Windows: ICMP port-unreachable após o outro lado fechar
            if src == self.receiver_addr:
                ack_count += 1
                if self.drop_ack_every and ack_count % self.drop_ack_every == 0:
                    continue
                self.sock.sendto(pkt, self.sender_addr)
            else:
                data_count += 1
                if self.drop_data_every and data_count % self.drop_data_every == 0:
                    continue
                if (self.reorder_data_every
                        and data_count % self.reorder_data_every == 0
                        and pending is None):
                    pending = pkt           # segura este; sai na frente o próximo
                    continue
                self.sock.sendto(pkt, self.receiver_addr)
                if pending is not None:     # libera o segurado depois (troca a ordem)
                    self.sock.sendto(pending, self.receiver_addr)
                    pending = None

    def stop(self):
        self._stop_evt.set()
        self.join(timeout=1)
        self.sock.close()


class TestModes(unittest.TestCase):
    def _transfer(self, mode, window, base, size=15123, **impair):
        d = tempfile.mkdtemp()
        infile = os.path.join(d, "in.bin")
        outfile = os.path.join(d, "out.bin")
        with open(infile, "wb") as f:
            f.write(bytes(i % 256 for i in range(size)))

        proxy_port = base
        receiver_port = base - 1  # receiver_port = proxy_port - 1 so the receiver's P+1 control lands on the proxy

        proxy = ImpairProxy(proxy_port, receiver_port, **impair)
        proxy.start()
        rx = threading.Thread(
            target=run_receiver, args=(receiver_port,),
            kwargs={"outpath": outfile, "mode": mode, "window": window},
            daemon=True)
        rx.start()

        run_sender("127.0.0.1", proxy_port, infile, mode=mode, window=window)
        rx.join(timeout=40)
        proxy.stop()
        self.assertFalse(rx.is_alive(), f"{mode}/w{window}: receiver não encerrou")
        self.assertEqual(sha256(infile), sha256(outfile),
                         f"{mode}/w{window}: arquivo difere do original")

    # ---- limpo (R0/P0), janelas 4 e 16 ----
    def test_gbn_limpo_w4(self):
        self._transfer("gbn", 4, 7600)

    def test_gbn_limpo_w16(self):
        self._transfer("gbn", 16, 7610)

    def test_sr_limpo_w4(self):
        self._transfer("sr", 4, 7620)

    def test_sr_limpo_w16(self):
        self._transfer("sr", 16, 7630)

    # ---- sob perda ----
    def test_gbn_perda_dados(self):
        self._transfer("gbn", 8, 7640, drop_data_every=7)

    def test_gbn_perda_acks(self):
        self._transfer("gbn", 8, 7650, drop_ack_every=6)

    def test_sr_perda_dados(self):
        self._transfer("sr", 8, 7660, drop_data_every=7)

    def test_sr_perda_acks(self):
        self._transfer("sr", 8, 7670, drop_ack_every=6)

    # ---- sob reordenação (ponto central da Parte 2) ----
    def test_gbn_reordenacao(self):
        self._transfer("gbn", 8, 7680, reorder_data_every=5)

    def test_sr_reordenacao(self):
        self._transfer("sr", 8, 7690, reorder_data_every=5)

    # ---- múltiplo exato de 255 (terminador Length=0) em janela ----
    def test_sr_multiplo_exato(self):
        self._transfer("sr", 8, 7700, size=255 * 60)

    def test_gbn_multiplo_exato(self):
        self._transfer("gbn", 8, 7710, size=255 * 60)


if __name__ == "__main__":
    unittest.main()
