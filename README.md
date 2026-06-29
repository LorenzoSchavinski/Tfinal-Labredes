# SRTP — Simple Reliable Transport Protocol (sobre UDP)

Transporte confiável sobre UDP. O mesmo programa suporta três modos
(`saw`, `gbn`, `sr`) via `--mode`.

## Requisitos

- Python 3.11+. Apenas biblioteca padrão, sem build/compilação.

## Como executar

Em duas máquinas distintas da rede local:

```bash
# Receiver (escuta na porta P = 6000):
python srtp.py --listen --port 6000 --out recebido.bin --mode gbn --window 16

# Sender (envia o arquivo ao receiver):
python srtp.py --host <IP_DO_RECEIVER> --port 6000 --file arquivo.bin --mode gbn --window 16
```

Os dois lados devem usar o mesmo `--mode`. A janela efetiva é
`min(--window do sender, --window do receiver)`, negociada no handshake.

## Argumentos de linha de comando

| Argumento | Modo | Descrição |
|---|---|---|
| `--listen` | receiver | Ativa o modo receiver (escuta na porta P). |
| `--host IP` | sender | IP do receiver. |
| `--port P` | ambos | Porta base P. |
| `--file caminho` | sender | Arquivo a transferir. |
| `--out caminho` | receiver | Arquivo de saída (default: `received.bin`). |
| `--mode saw\|gbn\|sr` | ambos | Modo do protocolo (default: `saw`). |
| `--window N` | ambos | Janela proposta no handshake, 1–255 (default: 1). |

## Notas

- `saw` é stop-and-wait (janela sempre 1); `gbn` é Go-Back-N (ACK cumulativo);
  `sr` é Selective Repeat (ACK individual, bufferiza fora de ordem).
- Janela válida no intervalo 1–255.
- O receiver escuta na porta P; após o handshake o sender recebe ACKs na porta P+1.
