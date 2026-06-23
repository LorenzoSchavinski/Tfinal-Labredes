"""
Harness de medição local para o relatório.

Roda transferências saw/gbn/sr localmente através de um proxy que injeta
latência, perda ou reordenação, e imprime throughput medido + retransmissões.
Também calcula o throughput TEÓRICO para confrontar com o medido.

Uso:
    python bench.py                      # tabela rápida dos três modos (limpo)
    python bench.py --mode gbn --window 16 --latency 0.05
    python bench.py --mode sr  --window 4  --loss 10 --size 30000

Observação: as MEDIÇÕES OFICIAIS do trabalho são entre duas máquinas distintas
com o clumsy + Wireshark (.pcapng). Este harness serve para sanity-check local e
para entender as tendências antes do lab.
"""
import argparse
import os
import socket
import tempfile
import threading
import time

from receiver import run_receiver
from sender import run_sender, TIMEOUT
from packet import HEADER_SIZE, MAX_PAYLOAD

PKT_BITS = (HEADER_SIZE + MAX_PAYLOAD) * 8   # bits por pacote cheio (no fio)


def throughput_teorico(rtt, window, link_bps=None):
    """Throughput teórico (bits/s) de ARQ com janela (Kurose & Ross, 3.4).

    Stop-and-wait é o caso window=1. Sem perda:
        U = window * (L/R) / (RTT + L/R), limitado por R (link_bps).
    Aqui L/R (tempo de transmissão) é desprezível em localhost; usamos o modelo
    dominado por RTT: vazão ~= window * L / RTT (bits/s), onde L é o pacote no fio.
    """
    if rtt <= 0:
        return float("inf")
    return window * PKT_BITS / rtt


class DelayLossProxy(threading.Thread):
    """Proxy UDP com latência fixa, perda determinística e reordenação."""

    def __init__(self, listen_port, receiver_port,
                 latency=0.0, loss_pct=0, reorder_pct=0):
        super().__init__(daemon=True)
        self.sender_addr = ("127.0.0.1", listen_port + 1)
        self.receiver_addr = ("127.0.0.1", receiver_port)
        self.latency = latency
        self.loss_pct = loss_pct
        self.reorder_pct = reorder_pct
        self._stop = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", listen_port))
        self.sock.settimeout(0.005)
        self._n = 0          # contador determinístico (sem random, p/ reprodutibilidade)
        self._delayed = []   # fila FIFO de (deadline, pkt, dest) — latência preserva ordem

    def _deliver(self, pkt, dest):
        if self.latency > 0:
            self._delayed.append((time.monotonic() + self.latency, pkt, dest))
        else:
            self.sock.sendto(pkt, dest)

    def _flush_due(self):
        now = time.monotonic()
        while self._delayed and self._delayed[0][0] <= now:
            _, pkt, dest = self._delayed.pop(0)
            self.sock.sendto(pkt, dest)

    def run(self):
        pending = None
        while not self._stop.is_set():
            self._flush_due()
            try:
                pkt, src = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue  # Windows: ICMP port-unreachable após o outro lado fechar
            dest = self.sender_addr if src == self.receiver_addr else self.receiver_addr
            self._n += 1
            # perda determinística: 1 a cada round(100/loss) pacotes
            if self.loss_pct and self._n % max(1, round(100 / self.loss_pct)) == 0:
                continue
            if (self.reorder_pct and src != self.receiver_addr
                    and self._n % max(1, round(100 / self.reorder_pct)) == 0
                    and pending is None):
                pending = (pkt, dest)
                continue
            self._deliver(pkt, dest)
            if pending is not None:
                self._deliver(*pending)
                pending = None

    def stop(self):
        self._stop.set()
        self.join(timeout=1)
        self.sock.close()


def run_once(mode, window, size, latency, loss, reorder, base=8200):
    d = tempfile.mkdtemp()
    infile = os.path.join(d, "in.bin")
    outfile = os.path.join(d, "out.bin")
    with open(infile, "wb") as f:
        f.write(bytes(i % 256 for i in range(size)))

    proxy = DelayLossProxy(base, base + 50, latency, loss, reorder)
    proxy.start()

    rx = threading.Thread(
        target=run_receiver,
        kwargs={"port": base + 50, "outpath": outfile, "mode": mode,
                "window": window, "verbose": False},
        daemon=True)
    rx.start()

    start = time.monotonic()
    stats = run_sender("127.0.0.1", base, infile, mode=mode, window=window,
                       verbose=False)
    rx.join(timeout=60)
    elapsed = time.monotonic() - start
    proxy.stop()

    rt = stats["rt"]
    ok = (os.path.getsize(infile) == os.path.getsize(outfile))
    meas = (size * 8 / elapsed) if elapsed > 0 else 0
    rtt = 2 * latency
    teo = throughput_teorico(rtt, window) if latency > 0 else float("inf")
    return meas, rt, ok, teo


def main():
    ap = argparse.ArgumentParser(description="Harness de medição local do SRTP")
    ap.add_argument("--mode", choices=["saw", "gbn", "sr"])
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--size", type=int, default=30000)
    ap.add_argument("--latency", type=float, default=0.0, help="latência por sentido (s)")
    ap.add_argument("--loss", type=float, default=0, help="perda (porcentagem)")
    ap.add_argument("--reorder", type=float, default=0, help="reordenacao (porcentagem)")
    args = ap.parse_args()

    print(f"{'modo':5} {'jan':>4} {'medido(kbps)':>13} {'teorico(kbps)':>14} "
          f"{'retr':>5} {'ok':>3}")
    combos = ([(args.mode, args.window)] if args.mode
              else [("saw", 1), ("gbn", 4), ("gbn", 16), ("sr", 4), ("sr", 16)])
    for k, (mode, window) in enumerate(combos):
        meas, rt, ok, teo = run_once(mode, window, args.size,
                                     args.latency, args.loss, args.reorder,
                                     base=8200 + k * 100)
        teo_s = "inf" if teo == float("inf") else f"{teo / 1000:13.1f}"
        print(f"{mode:5} {window:>4} {meas / 1000:13.1f} {teo_s:>14} "
              f"{rt:>5} {'sim' if ok else 'NAO':>3}")


if __name__ == "__main__":
    main()
