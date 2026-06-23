"""
Receiver do RTP — stop-and-wait (saw), Go-Back-N (gbn) e Selective Repeat (sr).

Fluxo comum: handshake (3 vias) -> recepção (depende do modo) -> entrega do
arquivo -> FIN+ACK. Escuta na porta P e responde sempre para o endereço de
origem (a porta P+1 do sender).

Formato de fio: ver sender.py.
"""
import socket
import time

from packet import Packet, MAX_PAYLOAD, SEQ_SPACE, SEQ_MASK

IDLE_TIMEOUT = 10.0  # segurança: desiste se o sender sumir por muito tempo


def _handshake(sock, window, verbose=True):
    """Espera o SYN, responde SYN+ACK. Retorna (sender_addr, synack_bytes, janela)."""
    sender_addr = None
    while sender_addr is None:
        data, addr = sock.recvfrom(2048)
        syn = Packet.from_bytes(data)
        if syn.crc_ok and syn.syn:
            sender_addr = addr
            sender_window = syn.length if syn.length else 1
    synack = Packet(syn=True, ack_flag=True, length=window).to_bytes()
    sock.sendto(synack, sender_addr)
    effective = min(window, sender_window)
    if verbose:
        print(f"[receiver] handshake ok, janela efetiva = {effective}")
    return sender_addr, synack, effective


# --------------------------------------------------------------------------
# Stop-and-Wait
# --------------------------------------------------------------------------
def _recv_saw(sock, addr, synack, window, state):
    buffer = state["buffer"]
    expected = 0
    while True:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            print("[receiver] timeout de inatividade — encerrando")
            return
        p = Packet.from_bytes(data)
        if not p.crc_ok:
            state["corrupt"] += 1
            continue
        if p.syn:
            sock.sendto(synack, addr)
            continue
        if p.ack_flag and not p.fin:
            continue
        if p.fin:
            sock.sendto(Packet(fin=True, ack_flag=True).to_bytes(), addr)
            return
        # dados
        if p.seq == expected % SEQ_SPACE:
            if state["start"] is None:
                state["start"] = time.monotonic()
            if not state["done"]:
                buffer.append(p.payload)
                state["bytes"] += len(p.payload)
            sock.sendto(Packet(ack=expected % SEQ_SPACE, ack_flag=True).to_bytes(), addr)
            if p.length < MAX_PAYLOAD:
                state["done"] = True
            expected += 1
        elif p.seq == (expected - 1) % SEQ_SPACE:
            state["dups"] += 1
            sock.sendto(Packet(ack=p.seq, ack_flag=True).to_bytes(), addr)
        else:
            state["ooo"] += 1


# --------------------------------------------------------------------------
# Go-Back-N
# --------------------------------------------------------------------------
def _recv_gbn(sock, addr, synack, window, state):
    buffer = state["buffer"]
    expected = 0          # índice absoluto esperado, em ordem
    while True:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            print("[receiver] timeout de inatividade — encerrando")
            return
        p = Packet.from_bytes(data)
        if not p.crc_ok:
            state["corrupt"] += 1
            continue
        if p.syn:
            sock.sendto(synack, addr)
            continue
        if p.ack_flag and not p.fin:
            continue
        if p.fin:
            sock.sendto(Packet(fin=True, ack_flag=True).to_bytes(), addr)
            return
        # dados
        exp_wire = expected % SEQ_SPACE
        if p.seq == exp_wire:                      # em ordem -> aceita
            if state["start"] is None:
                state["start"] = time.monotonic()
            if not state["done"]:
                buffer.append(p.payload)
                state["bytes"] += len(p.payload)
            if p.length < MAX_PAYLOAD:
                state["done"] = True
            expected += 1
            sock.sendto(Packet(ack=exp_wire, ack_flag=True).to_bytes(), addr)
        else:
            diff = (p.seq - exp_wire) & SEQ_MASK
            if 0 < diff <= window:                 # adiantado (lacuna) -> NACK
                state["ooo"] += 1
                sock.sendto(Packet(nack=True, ack=exp_wire).to_bytes(), addr)
            else:                                  # duplicata antiga -> re-ACK cumulativo
                state["dups"] += 1
                if expected > 0:
                    sock.sendto(
                        Packet(ack=(expected - 1) % SEQ_SPACE, ack_flag=True).to_bytes(),
                        addr)


# --------------------------------------------------------------------------
# Selective Repeat
# --------------------------------------------------------------------------
def _recv_sr(sock, addr, synack, window, state):
    buffer = state["buffer"]
    expected = 0          # base da janela de recepção (índice absoluto)
    buf = {}              # índice absoluto -> payload (fora de ordem, bufferizado)
    last_abs = None       # índice do último pacote do stream (Length < 255)

    def deliver():
        nonlocal expected
        while expected in buf:
            payload = buf.pop(expected)
            if not state["done"]:
                buffer.append(payload)
                state["bytes"] += len(payload)
            if expected == last_abs:
                state["done"] = True
            expected += 1

    while True:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            print("[receiver] timeout de inatividade — encerrando")
            return
        p = Packet.from_bytes(data)
        if not p.crc_ok:
            state["corrupt"] += 1
            continue
        if p.syn:
            sock.sendto(synack, addr)
            continue
        if p.ack_flag and not p.fin:
            continue
        if p.fin:
            sock.sendto(Packet(fin=True, ack_flag=True).to_bytes(), addr)
            return
        # dados
        exp_wire = expected % SEQ_SPACE
        r = (p.seq - exp_wire) & SEQ_MASK
        if r < window:                             # dentro da janela de recepção
            abs_idx = expected + r
            if state["start"] is None:
                state["start"] = time.monotonic()
            if abs_idx not in buf and abs_idx >= expected:
                buf[abs_idx] = p.payload
                if p.length < MAX_PAYLOAD:
                    last_abs = abs_idx
            # ACK individual do pacote recebido
            sock.sendto(Packet(ack=p.seq, ack_flag=True).to_bytes(), addr)
            if r > 0:                              # lacuna -> NACK(faltante = base)
                state["ooo"] += 1
                sock.sendto(Packet(nack=True, ack=exp_wire).to_bytes(), addr)
            deliver()
        else:                                      # fora da janela: duplicata antiga
            state["dups"] += 1
            sock.sendto(Packet(ack=p.seq, ack_flag=True).to_bytes(), addr)


_DISPATCH = {"saw": _recv_saw, "gbn": _recv_gbn, "sr": _recv_sr}


def run_receiver(port, outpath="received.bin", mode="saw", window=1, verbose=True):
    if mode not in _DISPATCH:
        raise ValueError(f"modo desconhecido: {mode}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))

    addr, synack, effective_window = _handshake(sock, window, verbose)

    sock.settimeout(IDLE_TIMEOUT)
    state = {"buffer": [], "bytes": 0, "corrupt": 0, "ooo": 0,
             "dups": 0, "start": None, "done": False}

    _DISPATCH[mode](sock, addr, synack, effective_window, state)

    elapsed = (time.monotonic() - state["start"]) if state["start"] else 0
    sock.close()

    with open(outpath, "wb") as f:
        f.write(b"".join(state["buffer"]))

    throughput = (state["bytes"] * 8 / elapsed) if elapsed > 0 else 0
    if verbose:
        print(f"[receiver] modo={mode} recebidos {state['bytes']} bytes -> {outpath}")
        print(f"[receiver] tempo: {elapsed:.3f}s | throughput: {throughput / 1000:.1f} kbit/s")
        print(f"[receiver] duplicatas: {state['dups']} | fora de ordem: {state['ooo']} "
              f"| corrompidos: {state['corrupt']}")
    return {"bytes": state["bytes"], "elapsed": elapsed, "dups": state["dups"],
            "ooo": state["ooo"], "corrupt": state["corrupt"]}
