"""
Relay UDP que corrompe exatamente UM pacote de dados do SRTP.

O clumsy injeta latência/perda/reordenação, mas não altera o payload. Para a
captura de demonstração do CRC32 (saw_crc.pcapng) precisamos de um pacote com
o CRC inválido: o receiver deve descartá-lo em silêncio (sem NACK) e o sender
retransmite por timeout. Este proxy fica no caminho sender -> receiver, repassa
tudo nos dois sentidos e vira UM byte do payload do N-ésimo pacote de dados.

Pacote de dados = SYN=0, FIN=0 (bits 31 e 30 da primeira palavra de 32 bits do
cabeçalho de 9 bytes). Handshake (SYN/SYN+ACK/ACK) e FIN passam intactos.

A porta do receiver tem que ser exatamente uma a menos que o --listen-port do
relay (receiver_port = relay_listen_port - 1), pois o receiver manda seus ACKs
para P+1, que precisa ser a porta de escuta do relay para os ACKs voltarem ao
sender.

Uso (3 terminais/máquinas):
    # receiver normal na porta P=6000 (ACKs vão para P+1 = 6001)
    python srtp.py --listen --port 6000 --out recebido.bin --mode saw

    # proxy: escuta em 6001 (= P+1 do receiver) e repassa para o receiver em 6000
    python corrupt.py --listen-port 6001 --target-host <IP_RECEIVER> --target-port 6000

    # sender aponta para o proxy (host = IP da máquina do proxy, port = 6001)
    python srtp.py --host <IP_PROXY> --port 6001 --file teste.bin --mode saw
"""
import argparse
import socket
import struct
import sys


def is_data_packet(data):
    """True se o datagrama é um pacote de dados COM payload (> 9 bytes), sem
    SYN nem FIN. ACKs/NACKs vêm do receiver no outro sentido."""
    if len(data) <= 9:
        return False
    (word,) = struct.unpack(">I", data[:4])
    syn = (word >> 31) & 1
    fin = (word >> 30) & 1
    return not syn and not fin


def corrupt(data):
    """Vira o bit menos significativo do primeiro byte de payload (offset 9),
    quebrando o CRC32 que cobre cabeçalho + payload."""
    b = bytearray(data)
    b[9] ^= 0x01
    return bytes(b)


def main():
    ap = argparse.ArgumentParser(description="Relay UDP que corrompe 1 pacote de dados (demo CRC32)")
    ap.add_argument("--listen-port", type=int, required=True, help="porta onde o sender envia")
    ap.add_argument("--target-host", required=True, help="IP do receiver")
    ap.add_argument("--target-port", type=int, required=True, help="porta P do receiver")
    ap.add_argument("--which", type=int, default=1, help="índice (1-based) do pacote de dados a corromper")
    args = ap.parse_args()

    target = (args.target_host, args.target_port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", args.listen_port))

    sender_addr = None   # aprendido no primeiro datagrama; ACKs voltam pra cá
    data_seen = 0        # quantos pacotes de dados já passaram
    done = False         # já corrompemos o pacote escolhido

    print(f"[corrupt] relay {args.listen_port} -> {target}, corrompe o pacote de dados #{args.which}")
    while True:
        data, src = sock.recvfrom(2048)
        if src == target:
            # tráfego do receiver (ACK/NACK/SYN+ACK/FIN+ACK) -> volta pro sender
            if sender_addr:
                sock.sendto(data, sender_addr)
            continue
        # tráfego do sender -> receiver
        sender_addr = src
        if not done and is_data_packet(data):
            data_seen += 1
            if data_seen == args.which:
                data = corrupt(data)
                done = True
                print(f"[corrupt] pacote de dados #{data_seen} corrompido (CRC32 deve falhar no receiver)")
        sock.sendto(data, target)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
