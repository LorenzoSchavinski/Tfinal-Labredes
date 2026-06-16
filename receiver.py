"""
Receiver stop-and-wait do RTP.

Fluxo: handshake (3 vias) -> recebe os pacotes em ordem -> entrega o arquivo
-> responde FIN+ACK. Escuta na porta P e responde sempre para o endereço de
origem (que é a porta P+1 do sender).
"""
import socket
import time

from packet import Packet, MAX_PAYLOAD, SEQ_SPACE

IDLE_TIMEOUT = 10.0  # segurança: desiste se o sender sumir por muito tempo


def run_receiver(port, outpath="received.bin", mode="saw", window=1):
    if mode != "saw":
        raise NotImplementedError(f"modo '{mode}' ainda não implementado (Parte 2)")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))

    # ---- Handshake: espera o SYN ----
    sock.settimeout(IDLE_TIMEOUT)
    sender_addr = None
    while sender_addr is None:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            print("[receiver] timeout aguardando SYN — encerrando")
            sock.close()
            return
        syn = Packet.from_bytes(data)
        if syn.crc_ok and syn.syn:
            sender_addr = addr
            sender_window = syn.length if syn.length else 1
    synack = Packet(syn=True, ack_flag=True, length=window)
    sock.sendto(synack.to_bytes(), sender_addr)
    effective_window = min(window, sender_window)
    print(f"[receiver] handshake ok, janela efetiva = {effective_window}")

    # ---- Recepção dos dados ----
    buffer = []
    expected_seq = 0
    stream_done = False
    total_bytes = 0
    corrupt = 0
    out_of_order = 0
    duplicates = 0
    start = None

    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            print("[receiver] timeout de inatividade — encerrando")
            break

        p = Packet.from_bytes(data)
        if not p.crc_ok:
            corrupt += 1          # corrompido: descarta em silêncio (sem NACK)
            continue
        if p.syn:                 # SYN+ACK se perdeu; reenvia
            sock.sendto(synack.to_bytes(), sender_addr)
            continue
        if p.ack_flag and not p.fin:
            continue              # ACK do handshake atrasado: ignora
        if p.fin:                 # encerramento
            finack = Packet(fin=True, ack_flag=True)
            sock.sendto(finack.to_bytes(), sender_addr)
            break

        # --- pacote de dados ---
        if p.seq == expected_seq:
            if start is None:
                start = time.monotonic()
            if not stream_done:
                buffer.append(p.payload)
                total_bytes += len(p.payload)
            # ACK cumulativo do pacote esperado
            sock.sendto(Packet(ack=expected_seq, ack_flag=True).to_bytes(), sender_addr)
            if p.length < MAX_PAYLOAD:   # último pacote do stream (inclui Length=0)
                stream_done = True
            expected_seq = (expected_seq + 1) % SEQ_SPACE
        elif p.seq == (expected_seq - 1) % SEQ_SPACE:
            # retransmissão por ACK perdido: re-envia o ACK, não rebufferiza
            duplicates += 1
            sock.sendto(Packet(ack=p.seq, ack_flag=True).to_bytes(), sender_addr)
        else:
            out_of_order += 1     # fora de ordem: descarta em silêncio

    elapsed = (time.monotonic() - start) if start else 0
    sock.close()

    with open(outpath, "wb") as f:
        f.write(b"".join(buffer))

    throughput = (total_bytes * 8 / elapsed) if elapsed > 0 else 0
    print(f"[receiver] recebidos {total_bytes} bytes -> {outpath}")
    print(f"[receiver] tempo: {elapsed:.3f}s | throughput: {throughput / 1000:.1f} kbit/s")
    print(f"[receiver] duplicatas: {duplicates} | fora de ordem: {out_of_order} "
          f"| corrompidos: {corrupt}")
