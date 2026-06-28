"""
Receiver do RTP — stop-and-wait (saw), Go-Back-N (gbn) e Selective Repeat (sr).

Fluxo comum: handshake (3 vias) -> recepção (depende do modo) -> entrega do
arquivo -> FIN+ACK. Escuta na porta P e, após o handshake, envia todo controle
(ACK, NACK, FIN+ACK) para (sender_ip, P+1), onde o sender escuta.

Formato de fio: ver sender.py.
"""
import socket
import struct
import time

from packet import Packet, MAX_PAYLOAD, SEQ_SPACE, SEQ_MASK

IDLE_TIMEOUT = 10.0  # segurança: desiste se o sender sumir por muito tempo


def _handshake(sock, window, verbose=True):
    """Espera o SYN, responde SYN+ACK. Retorna (sender_addr, synack_bytes, janela)."""
    sender_addr = None
    while sender_addr is None:
        try:
            data, addr = sock.recvfrom(2048)  # bloqueia aguardando o primeiro SYN (comportamento de listener)
        except ConnectionResetError:
            continue  # Windows: ICMP port-unreachable de um envio anterior; ignora e re-tenta
        try:
            syn = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue
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
def _recv_saw(sock, syn_addr, synack, control_addr, window, state):
    buffer = state["buffer"]
    expected = 0
    while True:
        try:
            data, src = sock.recvfrom(2048)
        except ConnectionResetError:
            continue  # Windows: ICMP port-unreachable de um envio anterior; ignora e re-tenta
        except socket.timeout:
            print("[receiver] timeout de inatividade — encerrando")
            return
        try:
            p = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue  # datagrama curto/ilegível: descarta em silêncio (interop)
        if not p.crc_ok:
            state["corrupt"] += 1
            continue
        if p.syn:
            # SYN retransmitido: o sender ainda completa o handshake no socket
            # de handshake (não em P+1). Re-responde para a origem do pacote.
            sock.sendto(synack, src)
            continue
        if p.ack_flag and not p.fin:
            continue
        if p.fin:
            sock.sendto(Packet(fin=True, ack_flag=True).to_bytes(), control_addr)
            _linger_close(sock, control_addr)
            return
        # dados
        if p.seq == expected % SEQ_SPACE:
            if state["start"] is None:
                state["start"] = time.monotonic()
            if not state["done"]:
                data_bytes = p.payload[:p.length]
                buffer.append(data_bytes)
                state["bytes"] += len(data_bytes)
            sock.sendto(Packet(ack=expected % SEQ_SPACE, ack_flag=True).to_bytes(), control_addr)
            if p.length < MAX_PAYLOAD:
                state["done"] = True
            expected += 1
        elif p.seq == (expected - 1) % SEQ_SPACE:
            state["dups"] += 1
            sock.sendto(Packet(ack=p.seq, ack_flag=True).to_bytes(), control_addr)
        else:
            state["ooo"] += 1


# --------------------------------------------------------------------------
# Go-Back-N
# --------------------------------------------------------------------------
def _recv_gbn(sock, syn_addr, synack, control_addr, window, state):
    buffer = state["buffer"]
    expected = 0          # índice absoluto esperado, em ordem
    while True:
        try:
            data, src = sock.recvfrom(2048)
        except ConnectionResetError:
            continue  # Windows: ICMP port-unreachable de um envio anterior; ignora e re-tenta
        except socket.timeout:
            print("[receiver] timeout de inatividade — encerrando")
            return
        try:
            p = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue  # datagrama curto/ilegível: descarta em silêncio (interop)
        if not p.crc_ok:
            state["corrupt"] += 1
            continue
        if p.syn:
            # SYN retransmitido: o sender ainda completa o handshake no socket
            # de handshake (não em P+1). Re-responde para a origem do pacote.
            sock.sendto(synack, src)
            continue
        if p.ack_flag and not p.fin:
            continue
        if p.fin:
            sock.sendto(Packet(fin=True, ack_flag=True).to_bytes(), control_addr)
            _linger_close(sock, control_addr)
            return
        # dados
        exp_wire = expected % SEQ_SPACE
        if p.seq == exp_wire:                      # em ordem -> aceita
            if state["start"] is None:
                state["start"] = time.monotonic()
            if not state["done"]:
                data_bytes = p.payload[:p.length]
                buffer.append(data_bytes)
                state["bytes"] += len(data_bytes)
            if p.length < MAX_PAYLOAD:
                state["done"] = True
            expected += 1
            sock.sendto(Packet(ack=exp_wire, ack_flag=True).to_bytes(), control_addr)
        else:
            diff = (p.seq - exp_wire) & SEQ_MASK
            if 0 < diff < window:                  # adiantado (lacuna) -> NACK
                state["ooo"] += 1
                sock.sendto(Packet(nack=True, ack=exp_wire).to_bytes(), control_addr)
            else:                                  # duplicata antiga -> re-ACK cumulativo
                state["dups"] += 1
                if expected > 0:
                    sock.sendto(
                        Packet(ack=(expected - 1) % SEQ_SPACE, ack_flag=True).to_bytes(),
                        control_addr)


# --------------------------------------------------------------------------
# Selective Repeat
# --------------------------------------------------------------------------
def _recv_sr(sock, syn_addr, synack, control_addr, window, state):
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
            data, src = sock.recvfrom(2048)
        except ConnectionResetError:
            continue  # Windows: ICMP port-unreachable de um envio anterior; ignora e re-tenta
        except socket.timeout:
            print("[receiver] timeout de inatividade — encerrando")
            return
        try:
            p = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue  # datagrama curto/ilegível: descarta em silêncio (interop)
        if not p.crc_ok:
            state["corrupt"] += 1
            continue
        if p.syn:
            # SYN retransmitido: o sender ainda completa o handshake no socket
            # de handshake (não em P+1). Re-responde para a origem do pacote.
            sock.sendto(synack, src)
            continue
        if p.ack_flag and not p.fin:
            continue
        if p.fin:
            sock.sendto(Packet(fin=True, ack_flag=True).to_bytes(), control_addr)
            _linger_close(sock, control_addr)
            return
        # dados
        exp_wire = expected % SEQ_SPACE
        r = (p.seq - exp_wire) & SEQ_MASK
        if r < window:                             # dentro da janela de recepção
            abs_idx = expected + r
            if state["start"] is None:
                state["start"] = time.monotonic()
            if abs_idx not in buf and abs_idx >= expected:
                # entrega exatamente Length bytes (spec): protege contra senders
                # de outros grupos que enviem o datagrama com padding além do Length.
                buf[abs_idx] = p.payload[:p.length]
                if p.length < MAX_PAYLOAD:
                    last_abs = abs_idx
            # ACK individual do pacote recebido
            sock.sendto(Packet(ack=p.seq, ack_flag=True).to_bytes(), control_addr)
            if r > 0:                              # lacuna -> NACK(faltante = base)
                state["ooo"] += 1
                sock.sendto(Packet(nack=True, ack=exp_wire).to_bytes(), control_addr)
            deliver()
        else:                                      # fora da janela: duplicata antiga
            state["dups"] += 1
            sock.sendto(Packet(ack=p.seq, ack_flag=True).to_bytes(), control_addr)


def _linger_close(sock, control_addr):
    """Janela de graça após o FIN+ACK: se o sender retransmitir o FIN (porque
    nosso FIN+ACK se perdeu), responde de novo para control_addr (P+1), onde o
    sender espera o fechamento.
    O sender reenvia o FIN a cada ~100ms; usamos um contador de períodos
    silenciosos consecutivos: 3 timeouts seguidos sem FIN (~300ms de silêncio)
    encerram a graça, e qualquer FIN respondido zera o contador para continuar
    atendendo retransmissões. O cap de 20 iterações (~2s) garante terminação."""
    sock.settimeout(0.1)
    finack = Packet(fin=True, ack_flag=True).to_bytes()
    quiet = 0
    for _ in range(20):
        try:
            data, src = sock.recvfrom(2048)
        except ConnectionResetError:
            continue  # Windows: ICMP port-unreachable de um envio anterior; ignora e re-tenta
        except socket.timeout:
            quiet += 1
            if quiet >= 3:
                return
            continue
        try:
            p = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue
        if p.crc_ok and p.fin:
            sock.sendto(finack, control_addr)
            quiet = 0


_DISPATCH = {"saw": _recv_saw, "gbn": _recv_gbn, "sr": _recv_sr}


def run_receiver(port, outpath="received.bin", mode="saw", window=1, verbose=True):
    if mode not in _DISPATCH:
        raise ValueError(f"modo desconhecido: {mode}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))

    syn_addr, synack, effective_window = _handshake(sock, window, verbose)

    # Spec: após o handshake o sender escuta ACKs/NACKs na porta P+1. Logo o
    # receiver mira (sender_ip, P+1) independentemente da porta de origem dos
    # pacotes de dados. É o que permite interoperar com um sender parceiro que
    # envia dados de um socket diferente do seu listener de ACK em P+1.
    control_addr = (syn_addr[0], port + 1)

    sock.settimeout(IDLE_TIMEOUT)
    state = {"buffer": [], "bytes": 0, "corrupt": 0, "ooo": 0,
             "dups": 0, "start": None, "done": False}

    _DISPATCH[mode](sock, syn_addr, synack, control_addr, effective_window, state)

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
