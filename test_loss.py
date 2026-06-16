"""
Teste de integração sob perda de pacotes.

Insere um proxy UDP entre sender e receiver que descarta pacotes de forma
determinística. Valida que a retransmissão por timeout e o re-ACK de duplicata
fazem a transferência terminar com o arquivo íntegro.

Topologia:
    sender (porta X+1) --dados--> proxy (porta X) --dados--> receiver (porta Y)
    sender (porta X+1) <--ACK---- proxy (porta X) <--ACK---- receiver (porta Y)
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


class LossyProxy(threading.Thread):
    """Encaminha pacotes entre sender e receiver, descartando alguns."""

    def __init__(self, listen_port, receiver_port, drop_data_every, drop_ack_every):
        super().__init__(daemon=True)
        self.listen_port = listen_port            # X (sender envia aqui)
        self.sender_addr = ("127.0.0.1", listen_port + 1)   # X+1 (ACKs vão pra cá)
        self.receiver_addr = ("127.0.0.1", receiver_port)   # Y
        self.drop_data_every = drop_data_every
        self.drop_ack_every = drop_ack_every
        self._stop_event = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", listen_port))
        self.sock.settimeout(0.2)

    def run(self):
        data_count = 0
        ack_count = 0
        while not self._stop_event.is_set():
            try:
                pkt, src = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            if src == self.receiver_addr:
                # ACK voltando para o sender
                ack_count += 1
                if self.drop_ack_every and ack_count % self.drop_ack_every == 0:
                    continue  # descarta este ACK
                self.sock.sendto(pkt, self.sender_addr)
            else:
                # dados indo para o receiver
                data_count += 1
                if self.drop_data_every and data_count % self.drop_data_every == 0:
                    continue  # descarta este dado
                self.sock.sendto(pkt, self.receiver_addr)

    def stop(self):
        self._stop_event.set()
        self.join(timeout=1)
        self.sock.close()


class TestUnderLoss(unittest.TestCase):
    def _transfer_with_loss(self, size, base, drop_data_every, drop_ack_every):
        d = tempfile.mkdtemp()
        infile = os.path.join(d, "in.bin")
        outfile = os.path.join(d, "out.bin")
        with open(infile, "wb") as f:
            f.write(bytes(i % 256 for i in range(size)))

        proxy_port = base          # sender envia aqui (X); escuta ACKs em X+1
        receiver_port = base + 50  # Y

        proxy = LossyProxy(proxy_port, receiver_port, drop_data_every, drop_ack_every)
        proxy.start()
        rx = threading.Thread(
            target=run_receiver, args=(receiver_port,),
            kwargs={"outpath": outfile}, daemon=True)
        rx.start()

        # sender "conecta" ao proxy (que encaminha para o receiver)
        run_sender("127.0.0.1", proxy_port, infile)
        rx.join(timeout=30)
        proxy.stop()
        self.assertFalse(rx.is_alive(), "receiver não encerrou")
        self.assertEqual(sha256(infile), sha256(outfile),
                         "arquivo recebido difere do original sob perda")

    def test_perda_de_dados(self):
        # descarta 1 a cada 5 pacotes de dados -> sender retransmite por timeout
        self._transfer_with_loss(15123, 7200, drop_data_every=5, drop_ack_every=0)

    def test_perda_de_acks(self):
        # descarta 1 a cada 4 ACKs -> exercita o re-ACK de duplicata no receiver
        self._transfer_with_loss(15123, 7300, drop_data_every=0, drop_ack_every=4)

    def test_perda_de_dados_e_acks(self):
        self._transfer_with_loss(15123, 7400, drop_data_every=3, drop_ack_every=3)


if __name__ == "__main__":
    unittest.main()
