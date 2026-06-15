"""
Cabeçalho RTP (9 bytes) — montagem, leitura e CRC32.

Layout dos 9 bytes (big-endian):

    Palavra de 32 bits (4 bytes):
        SYN(1) FIN(1) SEQ(14) ACKflag(1) NACK(1) ACK(14)
    Length (1 byte)
    CRC32  (4 bytes)

O CRC32 é calculado sobre o cabeçalho completo (com o campo CRC zerado)
concatenado com o payload.
"""
import struct
import zlib

HEADER_SIZE = 9          # bytes
MAX_PAYLOAD = 255        # bytes de payload por pacote de dados
SEQ_SPACE = 1 << 14      # 16384 -> SEQ/ACK de 14 bits (0..16383)
SEQ_MASK = SEQ_SPACE - 1  # 0x3FFF


class Packet:
    def __init__(self, seq=0, ack=0, syn=False, fin=False,
                 ack_flag=False, nack=False, length=0, payload=b""):
        self.seq = seq
        self.ack = ack
        self.syn = bool(syn)
        self.fin = bool(fin)
        self.ack_flag = bool(ack_flag)
        self.nack = bool(nack)
        self.length = length
        self.payload = payload
        self.crc_ok = True  # definido de verdade em from_bytes()

    def to_bytes(self):
        """Serializa o pacote (cabeçalho com CRC + payload)."""
        word = (
            (int(self.syn) << 31)
            | (int(self.fin) << 30)
            | ((self.seq & SEQ_MASK) << 16)
            | (int(self.ack_flag) << 15)
            | (int(self.nack) << 14)
            | (self.ack & SEQ_MASK)
        )
        # cabeçalho com CRC = 0 para o cálculo
        header_zero = struct.pack(">IBI", word, self.length & 0xFF, 0)
        crc = zlib.crc32(header_zero + self.payload) & 0xFFFFFFFF
        header = struct.pack(">IBI", word, self.length & 0xFF, crc)
        return header + self.payload

    @classmethod
    def from_bytes(cls, data):
        """Lê um pacote dos bytes recebidos; marca crc_ok se o CRC bate."""
        word, length, crc = struct.unpack(">IBI", data[:HEADER_SIZE])
        payload = data[HEADER_SIZE:]

        header_zero = struct.pack(">IBI", word, length, 0)
        crc_ok = (zlib.crc32(header_zero + payload) & 0xFFFFFFFF) == crc

        p = cls(
            seq=(word >> 16) & SEQ_MASK,
            ack=word & SEQ_MASK,
            syn=bool((word >> 31) & 1),
            fin=bool((word >> 30) & 1),
            ack_flag=bool((word >> 15) & 1),
            nack=bool((word >> 14) & 1),
            length=length,
            payload=payload,
        )
        p.crc_ok = crc_ok
        return p

    def __repr__(self):
        flags = "".join(f for f, on in (
            ("S", self.syn), ("F", self.fin),
            ("A", self.ack_flag), ("N", self.nack)) if on) or "-"
        return (f"Packet(seq={self.seq} ack={self.ack} flags={flags} "
                f"len={self.length} crc_ok={self.crc_ok})")
