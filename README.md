# SRTP — Simple Reliable Transport Protocol (sobre UDP)

Implementação do trabalho final de Laboratório de Redes de Computadores.
**Parte 1: stop-and-wait.** (GBN e SR virão na Parte 2.)

## Requisitos

- Python 3 (testado com 3.14). Sem dependências externas — usa apenas a
  biblioteca padrão (`socket`, `struct`, `zlib`).

## Como executar

Não precisa compilar. Em duas máquinas distintas da rede local:

```bash
# 1) No receiver (escuta na porta P = 6000):
python srtp.py --listen --port 6000 --out recebido.bin

# 2) No sender (envia um arquivo para o receiver):
python srtp.py --host <IP_DO_RECEIVER> --port 6000 --file arquivo.bin
```

O sender envia os dados para a porta `P` e escuta ACKs na porta `P+1`.

## Argumentos de linha de comando

| Argumento | Modo | Descrição |
|---|---|---|
| `--listen` | receiver | Ativa o modo receiver (escuta na porta P). |
| `--host IP` | sender | IP do receiver. |
| `--port P` | ambos | Porta base P (sender usa P+1 para receber ACKs). |
| `--file caminho` | sender | Arquivo a transferir. |
| `--out caminho` | receiver | Arquivo de saída (default: `received.bin`). |
| `--mode saw\|gbn\|sr` | ambos | Modo do protocolo (Parte 1: apenas `saw`). |
| `--window N` | ambos | Janela proposta no handshake (default: 1). |

Ao final, cada lado imprime bytes transferidos, tempo, throughput e número de
retransmissões — útil para o relatório.

## Estrutura do código

| Arquivo | Responsabilidade |
|---|---|
| `packet.py` | Cabeçalho RTP de 9 bytes: montagem, leitura e CRC32. |
| `sender.py` | Sender stop-and-wait: handshake, envio, FIN. |
| `receiver.py` | Receiver stop-and-wait: handshake, recepção, FIN. |
| `srtp.py` | CLI: lê argumentos e chama sender ou receiver. |
| `test_packet.py` | Testes unitários do cabeçalho/CRC. |

## Testes

```bash
python -m unittest test_packet -v
```

## Verificar integridade da transferência

O teste de interoperabilidade considera sucesso se o arquivo recebido for
idêntico ao original. Para conferir no Windows (PowerShell):

```powershell
Get-FileHash arquivo.bin, recebido.bin -Algorithm SHA256
```

No Linux/macOS:

```bash
sha256sum arquivo.bin recebido.bin   # os dois hashes devem ser iguais
```
