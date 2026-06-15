"""Testes do cabeçalho RTP (packet.py)."""
import unittest

from packet import Packet, HEADER_SIZE


class TestPacket(unittest.TestCase):
    def test_round_trip_data_packet(self):
        # Um pacote de dados deve voltar com todos os campos iguais.
        p = Packet(seq=42, length=255, payload=b"x" * 255)
        out = Packet.from_bytes(p.to_bytes())
        self.assertTrue(out.crc_ok)
        self.assertEqual(out.seq, 42)
        self.assertEqual(out.length, 255)
        self.assertEqual(out.payload, b"x" * 255)
        self.assertFalse(out.syn)
        self.assertFalse(out.fin)

    def test_header_size_is_9_bytes(self):
        p = Packet(seq=0, length=0, payload=b"")
        self.assertEqual(len(p.to_bytes()), HEADER_SIZE)

    def test_crc_detects_corruption(self):
        raw = bytearray(Packet(seq=1, length=255, payload=b"a" * 255).to_bytes())
        raw[-1] ^= 0xFF  # corrompe um byte do payload
        out = Packet.from_bytes(bytes(raw))
        self.assertFalse(out.crc_ok)

    def test_crc_detects_header_corruption(self):
        raw = bytearray(Packet(seq=7, length=255, payload=b"b" * 255).to_bytes())
        raw[0] ^= 0x01  # corrompe um byte do cabeçalho
        out = Packet.from_bytes(bytes(raw))
        self.assertFalse(out.crc_ok)

    def test_14_bit_seq_max(self):
        p = Packet(seq=16383, length=10, payload=b"c" * 10)
        out = Packet.from_bytes(p.to_bytes())
        self.assertEqual(out.seq, 16383)

    def test_14_bit_ack_max(self):
        p = Packet(ack=16383, ack_flag=True)
        out = Packet.from_bytes(p.to_bytes())
        self.assertEqual(out.ack, 16383)
        self.assertTrue(out.ack_flag)

    def test_flags_independentes(self):
        p = Packet(syn=True, fin=True, ack_flag=True, nack=True)
        out = Packet.from_bytes(p.to_bytes())
        self.assertTrue(out.syn)
        self.assertTrue(out.fin)
        self.assertTrue(out.ack_flag)
        self.assertTrue(out.nack)

    def test_handshake_packet_carrega_janela_em_length(self):
        # No SYN, Length transporta o tamanho de janela proposto.
        p = Packet(syn=True, length=16)
        out = Packet.from_bytes(p.to_bytes())
        self.assertTrue(out.syn)
        self.assertEqual(out.length, 16)

    def test_seq_faz_wrap_com_mascara(self):
        # SEQ acima do espaço de 14 bits deve ser mascarado (defensivo).
        p = Packet(seq=16384)  # == 0 no espaço de 14 bits
        out = Packet.from_bytes(p.to_bytes())
        self.assertEqual(out.seq, 0)


if __name__ == "__main__":
    unittest.main()
