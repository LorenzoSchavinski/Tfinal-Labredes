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
import hashlib
import os
import socket
import tempfile
import threading
import time

from receiver import run_receiver
from sender import run_sender, TIMEOUT
from packet import HEADER_SIZE, MAX_PAYLOAD

# ----------------------------------------------------------------------------
# MODELO CANÔNICO DE VAZÃO (deve bater exatamente com o relatório)
#
# Pacote no fio: header 9 bytes + payload. Pacote de dados cheio => payload 255 B.
#   L_wire = (9 + 255) * 8 = 2112 bits   (tamanho no fio)
#   L_pay  =       255  * 8 = 2040 bits   (payload útil)
# R       = taxa do enlace/canal em bits/s (parâmetro --rate; padrão LAN 1e9).
# t_trans = L_wire / R                     (tempo de transmissão de 1 pacote)
# RTT     = round-trip base + latência adicionada do cenário.
#
# Stop-and-wait (saw):
#   ciclo  = RTT + t_trans
#   U_sw   = t_trans / (RTT + t_trans)
#   G_sw   = L_pay / (RTT + t_trans)                       (goodput, bits/s úteis)
# Janela (gbn/sr), janela N:
#   U_win  = min(1, N * t_trans / (RTT + t_trans))
#   G_win  = min( R * L_pay / L_wire , N * L_pay / (RTT + t_trans) )
# Sob perda p (aproximação stop-and-wait): E[transmissões/pacote] = 1/(1-p), logo
#   G_sw_loss ~= G_sw * (1 - p)            (rotulado como APROXIMAÇÃO)
#
# Número primário = goodput de payload (G_*, bits úteis/s); também imprimimos a
# utilização do enlace U em %. Medido e teórico são a MESMA grandeza: bits de
# payload por segundo (goodput), não throughput no fio.
# ----------------------------------------------------------------------------
L_WIRE = (HEADER_SIZE + MAX_PAYLOAD) * 8   # 2112 bits: pacote de dados cheio no fio
L_PAY = MAX_PAYLOAD * 8                     # 2040 bits: payload útil por pacote


def goodput_teorico(mode, window, rtt, rate, loss_pct=0.0):
    """Goodput teórico (bits de payload/s) e utilização U do enlace.

    Usa exatamente as fórmulas do MODELO CANÔNICO acima. Retorna (G, U) onde G
    está em bits úteis/s e U em fração [0,1]. Para saw aplica a aproximação de
    perda G_sw * (1 - p); gbn/sr ignoram p (não modelado aqui).
    """
    t_trans = L_WIRE / rate
    cycle = rtt + t_trans
    if mode == "saw":
        g = L_PAY / cycle
        u = t_trans / cycle
        if loss_pct > 0:
            p = loss_pct / 100.0
            g *= (1 - p)          # aproximação: E[tx/pacote] = 1/(1-p)
        return g, u
    g = min(rate * L_PAY / L_WIRE, window * L_PAY / cycle)
    u = min(1.0, window * t_trans / cycle)
    return g, u


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
        self._stop_evt = threading.Event()
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
        while not self._stop_evt.is_set():
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
        self._stop_evt.set()
        self.join(timeout=1)
        self.sock.close()


def run_once(mode, window, size, latency, loss, reorder, rate, base_rtt, base=8200):
    d = tempfile.mkdtemp()
    infile = os.path.join(d, "in.bin")
    outfile = os.path.join(d, "out.bin")
    with open(infile, "wb") as f:
        f.write(bytes(i % 256 for i in range(size)))

    # receiver_port = proxy_port - 1 so the receiver's P+1 control lands on the proxy
    proxy = DelayLossProxy(base, base - 1, latency, loss, reorder)
    proxy.start()

    rx = threading.Thread(
        target=run_receiver,
        kwargs={"port": base - 1, "outpath": outfile, "mode": mode,
                "window": window, "verbose": False},
        daemon=True)
    rx.start()

    stats = run_sender("127.0.0.1", base, infile, mode=mode, window=window,
                       verbose=False)
    rx.join(timeout=60)
    proxy.stop()

    rt = stats["rt"]
    # elapsed da fase de dados do sender (sem handshake/close), p/ casar com o teórico.
    data_elapsed = stats["elapsed"]
    # interoperabilidade = conteúdo byte-a-byte idêntico (hash), não só tamanho:
    # uma saída corrompida de mesmo tamanho deve contar como falha.
    if os.path.exists(outfile):
        with open(infile, "rb") as f:
            in_hash = hashlib.sha256(f.read()).hexdigest()
        with open(outfile, "rb") as f:
            out_hash = hashlib.sha256(f.read()).hexdigest()
        ok = (in_hash == out_hash)
    else:
        ok = False
    # goodput medido: bits de PAYLOAD (conteúdo do arquivo) / s — mesma grandeza
    # que o teórico (não inclui os 9 B de header por pacote).
    meas = (size * 8 / data_elapsed) if data_elapsed > 0 else 0
    # RTT do cenário = round-trip base + latência adicionada nos dois sentidos.
    rtt = base_rtt + 2 * latency
    teo, util = goodput_teorico(mode, window, rtt, rate, loss)
    return meas, rt, ok, teo, util


def main():
    ap = argparse.ArgumentParser(description="Harness de medição local do SRTP")
    ap.add_argument("--mode", choices=["saw", "gbn", "sr"])
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--size", type=int, default=30000)
    ap.add_argument("--latency", type=float, default=0.0, help="latência por sentido (s)")
    ap.add_argument("--loss", type=float, default=0, help="perda (porcentagem)")
    ap.add_argument("--reorder", type=float, default=0, help="reordenacao (porcentagem)")
    ap.add_argument("--rate", type=float, default=1e9,
                    help="taxa do enlace R em bits/s (SUPOSIÇÃO; padrão 1e9 = 1 Gb/s LAN)")
    ap.add_argument("--base-rtt", type=float, default=2e-4,
                    help="RTT base do enlace em s p/ cenário L0 (SUPOSIÇÃO; padrão 0.2 ms localhost)")
    args = ap.parse_args()

    # Ambos medido e teórico são GOODPUT: bits de payload úteis/s (não no fio).
    print(f"{'modo':5} {'jan':>4} {'lat+(s)':>8} {'perda%':>6} {'reord%':>6} "
          f"{'medido(kbps)':>13} {'teorico(kbps)':>14} {'U%':>5} {'retr':>5} {'ok':>3}")
    combos = ([(args.mode, args.window)] if args.mode
              else [("saw", 1), ("gbn", 4), ("gbn", 16), ("sr", 4), ("sr", 16)])
    for k, (mode, window) in enumerate(combos):
        meas, rt, ok, teo, util = run_once(mode, window, args.size,
                                           args.latency, args.loss, args.reorder,
                                           args.rate, args.base_rtt,
                                           base=8200 + k * 100)
        print(f"{mode:5} {window:>4} {args.latency:8.3f} {args.loss:6.1f} "
              f"{args.reorder:6.1f} {meas / 1000:13.1f} {teo / 1000:14.1f} "
              f"{util * 100:5.1f} {rt:>5} {'sim' if ok else 'NAO':>3}")


if __name__ == "__main__":
    main()
