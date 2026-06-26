"""
Sender do RTP — stop-and-wait (saw), Go-Back-N (gbn) e Selective Repeat (sr).

Fluxo comum: handshake (3 vias) -> transferência (depende do modo) -> FIN (2 vias).
Envia tudo para (host, P) e escuta ACKs/NACKs no socket local da porta P+1.

Formato de fio (contrato com o outro grupo):
  - ACK positivo: ack_flag=True, nack=False, campo ack = seq.
      * saw/gbn: ack cumulativo = maior seq recebido em ordem.
      * sr: ack individual = seq exato aceito.
  - NACK: nack=True, ack_flag=False, campo ack = seq esperado (gbn) / faltante (sr).
"""
import socket
import struct
import time

from packet import Packet, MAX_PAYLOAD, SEQ_SPACE, SEQ_MASK

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


def _data_packet(chunks, i):
    """Monta o pacote de dados do índice absoluto i (seq = i % 16384)."""
    chunk = chunks[i]
    return Packet(seq=i % SEQ_SPACE, length=len(chunk), payload=chunk)


def _resolve_abs(wire_seq, base, nxt):
    """Mapeia um seq de 14 bits para o índice absoluto dentro de [base, nxt).

    A janela é <= 255 << 16384, então há no máximo um índice candidato.
    Retorna o índice absoluto ou None se não cair na janela em trânsito.
    """
    cand = base + ((wire_seq - base) & SEQ_MASK)
    return cand if base <= cand < nxt else None


# --------------------------------------------------------------------------
# Handshake (compartilhado pelos três modos)
# --------------------------------------------------------------------------
def _handshake(sock, dest, window, verbose=True):
    """Three-way handshake do lado iniciador. Retorna a janela efetiva."""
    syn = Packet(syn=True, length=window)
    raw = syn.to_bytes()
    sock.sendto(raw, dest)
    while True:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            sock.sendto(raw, dest)
            continue
        try:
            reply = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue
        if reply.crc_ok and reply.syn and reply.ack_flag:
            break
    effective = min(window, reply.length if reply.length else 1)
    sock.sendto(Packet(ack_flag=True).to_bytes(), dest)
    if verbose:
        print(f"[sender] handshake ok, janela efetiva = {effective}")
    return effective


def _close(sock, dest, stats):
    """Encerramento (2 vias): FIN -> FIN+ACK."""
    sock.settimeout(TIMEOUT)       # loops de dados alteram o timeout; FIN usa o fixo da spec
    fin = Packet(fin=True, length=0)
    raw = fin.to_bytes()
    sock.sendto(raw, dest)
    retries = 0
    while retries < 10:
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            retries += 1
            stats["rt"] += 1
            sock.sendto(raw, dest)
            continue
        try:
            p = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue
        if p.crc_ok and p.fin and p.ack_flag:
            break


# --------------------------------------------------------------------------
# Stop-and-Wait
# --------------------------------------------------------------------------
def _send_saw(sock, dest, chunks, window, stats):
    seq = 0
    for chunk in chunks:
        pkt = Packet(seq=seq, length=len(chunk), payload=chunk)
        raw = pkt.to_bytes()
        sock.sendto(raw, dest)
        while True:
            try:
                data, _ = sock.recvfrom(2048)
            except socket.timeout:
                stats["rt"] += 1
                sock.sendto(raw, dest)
                continue
            try:
                p = Packet.from_bytes(data)
            except (struct.error, ValueError):
                continue
            if not p.crc_ok:
                continue
            # SYN+ACK retransmitido (handshake): reenvia o 3o ACK e segue esperando.
            # Robustez de interop: nosso 3o ACK pode ter se perdido, e um SYN+ACK
            # tem ack_flag=1/ack=0, que seria confundido com o ACK do pacote seq 0.
            if p.syn and p.ack_flag:
                sock.sendto(Packet(ack_flag=True).to_bytes(), dest)   # reenvia o 3o ACK do handshake
                continue
            if p.fin:                          # FIN não é ACK de dados
                continue
            if p.ack_flag and p.ack == seq:
                break
            # NACK em saw não é esperado; timeout resolve.
        seq = (seq + 1) % SEQ_SPACE


# --------------------------------------------------------------------------
# Go-Back-N
# --------------------------------------------------------------------------
def _send_gbn(sock, dest, chunks, window, stats):
    W = max(1, window)
    M = len(chunks)
    base = 0           # índice absoluto do mais antigo não confirmado
    nxt = 0            # próximo índice absoluto a enviar
    timer = None       # deadline (monotonic) do timer da base

    def resend_window():
        for i in range(base, nxt):
            sock.sendto(_data_packet(chunks, i).to_bytes(), dest)
            stats["rt"] += 1

    while base < M:
        # enche a janela
        while nxt < base + W and nxt < M:
            sock.sendto(_data_packet(chunks, nxt).to_bytes(), dest)
            if base == nxt:
                timer = time.monotonic() + TIMEOUT
            nxt += 1

        remaining = (timer - time.monotonic()) if timer else TIMEOUT
        if remaining <= 0:
            resend_window()
            timer = time.monotonic() + TIMEOUT
            continue

        sock.settimeout(remaining)
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            resend_window()
            timer = time.monotonic() + TIMEOUT
            continue

        try:
            p = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue
        if not p.crc_ok:
            continue
        # SYN+ACK retransmitido (handshake): reenvia o 3o ACK e segue esperando.
        # Robustez de interop: nosso 3o ACK pode ter se perdido, e um SYN+ACK
        # tem ack_flag=1/ack=0, que cairia no ramo de ACK de dados abaixo.
        if p.syn and p.ack_flag:
            sock.sendto(Packet(ack_flag=True).to_bytes(), dest)   # reenvia o 3o ACK do handshake
            continue
        if p.fin:                          # FIN não é ACK de dados
            continue
        if p.nack:                         # NACK -> reenvia toda a janela
            resend_window()
            timer = time.monotonic() + TIMEOUT
            continue
        if p.ack_flag:                     # ACK cumulativo: confirma até p.ack
            acked = _resolve_abs(p.ack, base, nxt)
            if acked is not None:
                base = acked + 1
                timer = (time.monotonic() + TIMEOUT) if base < nxt else None


# --------------------------------------------------------------------------
# Selective Repeat
# --------------------------------------------------------------------------
def _send_sr(sock, dest, chunks, window, stats):
    W = max(1, window)
    M = len(chunks)
    base = 0
    nxt = 0
    acked = set()       # índices absolutos confirmados individualmente
    timers = {}         # índice absoluto -> deadline (monotonic)

    while base < M:
        # enche a janela
        while nxt < base + W and nxt < M:
            sock.sendto(_data_packet(chunks, nxt).to_bytes(), dest)
            timers[nxt] = time.monotonic() + TIMEOUT
            nxt += 1

        now = time.monotonic()
        due = [i for i, d in timers.items() if d <= now]
        if due:
            for i in due:
                sock.sendto(_data_packet(chunks, i).to_bytes(), dest)
                stats["rt"] += 1
                timers[i] = now + TIMEOUT
            continue

        remaining = (min(timers.values()) - now) if timers else TIMEOUT
        sock.settimeout(max(remaining, 0.001))
        try:
            data, _ = sock.recvfrom(2048)
        except socket.timeout:
            continue

        try:
            p = Packet.from_bytes(data)
        except (struct.error, ValueError):
            continue
        if not p.crc_ok:
            continue
        # SYN+ACK retransmitido (handshake): reenvia o 3o ACK e segue esperando.
        # Robustez de interop: nosso 3o ACK pode ter se perdido, e um SYN+ACK
        # tem ack_flag=1/ack=0, que cairia no ramo de ACK individual abaixo.
        if p.syn and p.ack_flag:
            sock.sendto(Packet(ack_flag=True).to_bytes(), dest)   # reenvia o 3o ACK do handshake
            continue
        if p.fin:                          # FIN não é ACK de dados
            continue
        if p.nack:                         # NACK(faltante) -> reenvia só aquele
            miss = _resolve_abs(p.ack, base, nxt)
            if miss is not None and miss in timers:
                sock.sendto(_data_packet(chunks, miss).to_bytes(), dest)
                stats["rt"] += 1
                timers[miss] = time.monotonic() + TIMEOUT
            continue
        if p.ack_flag:                     # ACK individual
            a = _resolve_abs(p.ack, base, nxt)
            if a is not None:
                acked.add(a)
                timers.pop(a, None)
                while base in acked:       # desliza por toda a faixa contígua
                    acked.discard(base)
                    base += 1


_DISPATCH = {"saw": _send_saw, "gbn": _send_gbn, "sr": _send_sr}


def run_sender(host, port, filepath, mode="saw", window=1, verbose=True):
    if mode not in _DISPATCH:
        raise ValueError(f"modo desconhecido: {mode}")

    with open(filepath, "rb") as f:
        data = f.read()

    dest = (host, port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port + 1))      # sender escuta ACKs/NACKs em P+1
    sock.settimeout(TIMEOUT)

    stats = {"rt": 0}

    effective_window = _handshake(sock, dest, window, verbose)
    chunks = _chunk_file(data)
    start = time.monotonic()       # cronometra só a fase de transferência de dados
    _DISPATCH[mode](sock, dest, chunks, effective_window, stats)
    elapsed = time.monotonic() - start    # mede só a transferência de dados, antes do encerramento
    _close(sock, dest, stats)
    sock.close()

    throughput = (len(data) * 8 / elapsed) if elapsed > 0 else 0
    if verbose:
        print(f"[sender] modo={mode} janela={effective_window} "
              f"enviados {len(data)} bytes em {len(chunks)} pacotes")
        print(f"[sender] tempo: {elapsed:.3f}s | throughput: {throughput / 1000:.1f} kbit/s")
        print(f"[sender] retransmissões: {stats['rt']}")
    return {"bytes": len(data), "packets": len(chunks), "elapsed": elapsed,
            "rt": stats["rt"], "window": effective_window}
