"""
Sender stop-and-wait do RTP.

Fluxo: handshake (3 vias) -> envia o arquivo um pacote por vez -> FIN (2 vias).
Envia tudo para (host, P) e escuta ACKs no socket local da porta P+1.
"""
import socket
import time

from packet import Packet, MAX_PAYLOAD, SEQ_SPACE

TIMEOUT = 0.1  # 100 ms (fixo, conforme a spec)


def _chunk_file(data):
    """Divide o arquivo em blocos de 255 bytes.

    Garante que o último bloco tenha length < 255 (sinal de fim de stream).
    Se o arquivo for múltiplo exato de 255 (ou vazio), acrescenta um bloco
    vazio (Length = 0) como terminador.
    """
    chunks = [data[i:i + MAX_PAYLOAD] for i in range(0, len(data), MAX_PAYLOAD)]
    if not chunks or len(chunks[-1]) == MAX_PAYLOAD:
        chunks.append(b"")
    return chunks


def _send_until(sock, dest, pkt, accept, max_retries=None):
    """Envia pkt e retransmite a cada TIMEOUT até accept(reply) ser True.

    Retorna (reply, retransmissoes). Se max_retries for atingido, retorna
    (None, retransmissoes).
    """
    raw = pkt.to_bytes()
    retransmissions = 0
    sock.sendto(raw, dest)
    while True:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            if max_retries is not None and retransmissions >= max_retries:
                return None, retransmissions
            retransmissions += 1
            sock.sendto(raw, dest)
            continue
        reply = Packet.from_bytes(data)
        if not reply.crc_ok:
            continue  # pacote corrompido: ignora e segue esperando
        if accept(reply):
            return reply, retransmissions


def run_sender(host, port, filepath, mode="saw", window=1):
    if mode != "saw":
        raise NotImplementedError(f"modo '{mode}' ainda não implementado (Parte 2)")

    with open(filepath, "rb") as f:
        data = f.read()

    dest = (host, port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port + 1))      # sender escuta ACKs/NACKs em P+1
    sock.settimeout(TIMEOUT)

    total_retransmissions = 0

    # ---- Handshake (3 vias) ----
    syn = Packet(syn=True, length=window)
    reply, rt = _send_until(sock, dest, syn,
                            lambda p: p.syn and p.ack_flag)
    total_retransmissions += rt
    effective_window = min(window, reply.length if reply.length else 1)
    sock.sendto(Packet(ack_flag=True).to_bytes(), dest)
    print(f"[sender] handshake ok, janela efetiva = {effective_window}")

    start = time.monotonic()  # mede só a transferência, não o handshake

    # ---- Transferência (stop-and-wait) ----
    chunks = _chunk_file(data)
    seq = 0
    for chunk in chunks:
        pkt = Packet(seq=seq, length=len(chunk), payload=chunk)
        _, rt = _send_until(sock, dest, pkt,
                            lambda p, s=seq: p.ack_flag and p.ack == s)
        total_retransmissions += rt
        seq = (seq + 1) % SEQ_SPACE

    # ---- Encerramento (2 vias) ----
    fin = Packet(fin=True, length=0)
    _, rt = _send_until(sock, dest, fin,
                        lambda p: p.fin and p.ack_flag, max_retries=10)
    total_retransmissions += rt

    elapsed = time.monotonic() - start
    sock.close()

    throughput = (len(data) * 8 / elapsed) if elapsed > 0 else 0
    print(f"[sender] enviados {len(data)} bytes em {len(chunks)} pacotes")
    print(f"[sender] tempo: {elapsed:.3f}s | throughput: {throughput / 1000:.1f} kbit/s")
    print(f"[sender] retransmissões: {total_retransmissions}")
