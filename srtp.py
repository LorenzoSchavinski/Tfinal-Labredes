"""
SRTP — protocolo de transporte confiável sobre UDP.

Ponto de entrada da linha de comando. Lê os argumentos e chama o sender ou o
receiver. Modos: stop-and-wait ('saw'), Go-Back-N ('gbn'), Selective Repeat ('sr').

Exemplos:
    # Receiver escutando na porta 6000
    python srtp.py --listen --port 6000 --out recebido.bin

    # Sender enviando um arquivo para o receiver
    python srtp.py --host 192.168.1.10 --port 6000 --file arquivo.bin
"""
import argparse

from receiver import run_receiver
from sender import run_sender


def main():
    parser = argparse.ArgumentParser(description="SRTP sobre UDP (saw | gbn | sr)")
    parser.add_argument("--listen", action="store_true",
                        help="modo receiver (escuta na porta P)")
    parser.add_argument("--host", help="IP do receiver (modo sender)")
    parser.add_argument("--port", type=int, required=True, help="porta P")
    parser.add_argument("--file", help="arquivo a enviar (modo sender)")
    parser.add_argument("--out", default="received.bin",
                        help="arquivo de saída (modo receiver)")
    parser.add_argument("--mode", default="saw", choices=["saw", "gbn", "sr"],
                        help="modo do protocolo: saw | gbn | sr")
    parser.add_argument("--window", type=int, default=1,
                        help="tamanho de janela proposto no handshake")
    args = parser.parse_args()

    if args.listen:
        run_receiver(args.port, outpath=args.out, mode=args.mode, window=args.window)
    else:
        if not args.host or not args.file:
            parser.error("modo sender exige --host e --file")
        run_sender(args.host, args.port, args.file, mode=args.mode, window=args.window)


if __name__ == "__main__":
    main()
