---

# Worksheet das capturas

Arranjo: **PC = sender + clumsy + wireshark**, **note = receiver**. Preencha `throughput` (kbit/s) e `retransm.` com os valores que o **sender** imprime ao terminar cada transferência (`[sender] throughput: ...` e `[sender] retransmissões: ...`).

Clumsy (no PC): marque a função, deixe **Inbound e Outbound** marcados, e ponha o valor. Filtro sugerido no clumsy: `udp.DstPort == 6000 or udp.SrcPort == 6000`. Nos baseline (L0, P0, R0) o clumsy fica **desligado**.

- Lag = latência, Drop = perda, Out of order = reordenação.

## Parte 1 — Stop-and-Wait (saw)
Receiver (note): `python srtp.py --listen --port 6000 --mode saw --out recebido.bin`
Sender (PC): `python srtp.py --host 192.168.1.26 --port 6000 --mode saw --file teste.bin`

| arquivo | clumsy | throughput | retransm. |
|---|---|---|---|
| saw_L0.pcapng | desligado | | |
| saw_L1.pcapng | Lag 50 ms | | |
| saw_L2.pcapng | Lag 100 ms | | |
| saw_L3.pcapng | Lag 150 ms | | |
| saw_P0.pcapng | desligado | | |
| saw_P1.pcapng | Drop 1% | | |
| saw_P2.pcapng | Drop 5% | | |
| saw_P3.pcapng | Drop 10% | | |
| saw_P4.pcapng | Drop 25% | | |

## Parte 2 — Go-Back-N, janela 4
Receiver (note): `python srtp.py --listen --port 6000 --mode gbn --window 4 --out recebido.bin`
Sender (PC): `python srtp.py --host 192.168.1.26 --port 6000 --mode gbn --window 4 --file teste.bin`

| arquivo | clumsy | throughput | retransm. |
|---|---|---|---|
| gbn_L0_janela4.pcapng | desligado | | |
| gbn_L1_janela4.pcapng | Lag 50 ms | | |
| gbn_L2_janela4.pcapng | Lag 100 ms | | |
| gbn_L3_janela4.pcapng | Lag 150 ms | | |
| gbn_P0_janela4.pcapng | desligado | | |
| gbn_P1_janela4.pcapng | Drop 1% | | |
| gbn_P2_janela4.pcapng | Drop 5% | | |
| gbn_P3_janela4.pcapng | Drop 10% | | |
| gbn_P4_janela4.pcapng | Drop 25% | | |
| gbn_R0_janela4.pcapng | desligado | | |
| gbn_R1_janela4.pcapng | Out of order 10% | | |
| gbn_R2_janela4.pcapng | Out of order 25% | | |

## Parte 2 — Go-Back-N, janela 16
Receiver (note): `python srtp.py --listen --port 6000 --mode gbn --window 16 --out recebido.bin`
Sender (PC): `python srtp.py --host 192.168.1.26 --port 6000 --mode gbn --window 16 --file teste.bin`

| arquivo | clumsy | throughput | retransm. |
|---|---|---|---|
| gbn_L0_janela16.pcapng | desligado | | |
| gbn_L1_janela16.pcapng | Lag 50 ms | | |
| gbn_L2_janela16.pcapng | Lag 100 ms | | |
| gbn_L3_janela16.pcapng | Lag 150 ms | | |
| gbn_P0_janela16.pcapng | desligado | | |
| gbn_P1_janela16.pcapng | Drop 1% | | |
| gbn_P2_janela16.pcapng | Drop 5% | | |
| gbn_P3_janela16.pcapng | Drop 10% | | |
| gbn_P4_janela16.pcapng | Drop 25% | | |
| gbn_R0_janela16.pcapng | desligado | | |
| gbn_R1_janela16.pcapng | Out of order 10% | | |
| gbn_R2_janela16.pcapng | Out of order 25% | | |

## Parte 2 — Selective Repeat, janela 4
Receiver (note): `python srtp.py --listen --port 6000 --mode sr --window 4 --out recebido.bin`
Sender (PC): `python srtp.py --host 192.168.1.26 --port 6000 --mode sr --window 4 --file teste.bin`

| arquivo | clumsy | throughput | retransm. |
|---|---|---|---|
| sr_L0_janela4.pcapng | desligado | | |
| sr_L1_janela4.pcapng | Lag 50 ms | | |
| sr_L2_janela4.pcapng | Lag 100 ms | | |
| sr_L3_janela4.pcapng | Lag 150 ms | | |
| sr_P0_janela4.pcapng | desligado | | |
| sr_P1_janela4.pcapng | Drop 1% | | |
| sr_P2_janela4.pcapng | Drop 5% | | |
| sr_P3_janela4.pcapng | Drop 10% | | |
| sr_P4_janela4.pcapng | Drop 25% | | |
| sr_R0_janela4.pcapng | desligado | | |
| sr_R1_janela4.pcapng | Out of order 10% | | |
| sr_R2_janela4.pcapng | Out of order 25% | | |

## Parte 2 — Selective Repeat, janela 16
Receiver (note): `python srtp.py --listen --port 6000 --mode sr --window 16 --out recebido.bin`
Sender (PC): `python srtp.py --host 192.168.1.26 --port 6000 --mode sr --window 16 --file teste.bin`

| arquivo | clumsy | throughput | retransm. |
|---|---|---|---|
| sr_L0_janela16.pcapng | desligado | | |
| sr_L1_janela16.pcapng | Lag 50 ms | | |
| sr_L2_janela16.pcapng | Lag 100 ms | | |
| sr_L3_janela16.pcapng | Lag 150 ms | | |
| sr_P0_janela16.pcapng | desligado | | |
| sr_P1_janela16.pcapng | Drop 1% | | |
| sr_P2_janela16.pcapng | Drop 5% | | |
| sr_P3_janela16.pcapng | Drop 10% | | |
| sr_P4_janela16.pcapng | Drop 25% | | |
| sr_R0_janela16.pcapng | desligado | | |
| sr_R1_janela16.pcapng | Out of order 10% | | |
| sr_R2_janela16.pcapng | Out of order 25% | | |

## Demonstração CRC32
Usa o relay corrupt.py (ver docs/runbook_capturas.md). Salvar como `saw_crc.pcapng`.

| arquivo | observação |
|---|---|
| saw_crc.pcapng | 1 pacote corrompido descartado + retransmissão |

Total: 58 arquivos .pcapng.

---
