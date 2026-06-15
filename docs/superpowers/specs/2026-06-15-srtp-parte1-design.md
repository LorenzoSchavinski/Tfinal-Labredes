# SRTP — Parte 1 (Stop-and-Wait) — Design

Implementação em **Python** de um protocolo de transporte confiável sobre UDP
(SRTP / RTP), conforme o enunciado do Trabalho Final de Laboratório de Redes.
Este documento cobre **apenas a Parte 1 (stop-and-wait)**. GBN e SR (Parte 2)
serão adicionados depois reutilizando o mesmo cabeçalho e handshake.

Objetivo de estilo: **código simples e legível**, fácil de explicar na
apresentação.

## Arquitetura

Quatro arquivos pequenos, cada um com um propósito único:

| Arquivo | Responsabilidade |
|---|---|
| `packet.py` | Monta/lê o cabeçalho de 9 bytes e calcula/verifica o CRC32. Todo o formato do protocolo está aqui. |
| `sender.py` | Lógica do sender stop-and-wait: handshake → envia arquivo → FIN. |
| `receiver.py` | Lógica do receiver stop-and-wait: handshake → recebe arquivo → FIN. |
| `srtp.py` | Entrada CLI: lê argumentos e chama sender ou receiver. |

## Cabeçalho (9 bytes)

Layout = 4 bytes (palavra de flags+SEQ+ACK) + 1 byte Length + 4 bytes CRC32.

Primeira palavra de 32 bits, big-endian, do bit mais significativo ao menos:

```
SYN(1) FIN(1) SEQ(14) ACKflag(1) NACK(1) ACK(14)
```

- Montagem: `word = (SYN<<31)|(FIN<<30)|(SEQ<<16)|(ACKflag<<15)|(NACK<<14)|ACK`
- Serialização: `struct.pack('>IBI', word, length, crc)`
- CRC32: `zlib.crc32(header_com_campo_crc_zerado + payload)` (unsigned, 32 bits)
- Leitura: caminho inverso com máscaras e shifts.

Campos:
- **SEQ** (14 bits, 0..16383): em pacotes, começa em 0 no 1º dado pós-handshake; wrap-around com `% 16384`.
- **SYN / FIN**: flags de abertura/fechamento.
- **ACK** (14 bits) + **ACKflag**: número e validade do acknowledgement.
- **NACK**: não usado na Parte 1 (reservado para Parte 2).
- **Length** (8 bits): na transferência = bytes de payload; no handshake = janela proposta.

### Semântica de Length na transferência
- `255` → pacote intermediário (receiver bufferiza e aguarda).
- `< 255` → último pacote do stream (receiver entrega o buffer à aplicação).
- `0` → arquivo é múltiplo exato de 255 bytes: fim de stream sem payload residual.

## Fluxos

### Handshake (3 vias)
1. Sender → SYN, `Length = janela_proposta`, SEQ=ACK=0.
2. Receiver → SYN+ACK, `Length = janela_do_receiver`.
3. Sender → ACK.

Janela efetiva = `min(janela_sender, janela_receiver)`. Em stop-and-wait a janela
não altera o comportamento (1 pacote em trânsito), mas é negociada para conformidade.
SYN e SYN+ACK são retransmitidos a cada 100 ms enquanto não houver resposta.

### Transferência (stop-and-wait)
- Sender lê o arquivo em blocos de 255 bytes; SEQ inicia em 0.
- Envia um pacote e aguarda o ACK daquele SEQ por **100 ms**.
- Timeout → retransmite o mesmo pacote.
- ACK correto → `SEQ = (SEQ+1) % 16384`, próximo bloco.
- Receiver valida CRC32 (descarta em silêncio se inválido — sem NACK), e:
  - SEQ == esperado → bufferiza, envia ACK(esperado), avança.
  - SEQ == esperado−1 (retransmissão por ACK perdido) → **re-envia ACK** sem rebufferizar.
  - Qualquer outro SEQ → descarta em silêncio.

> **Desvio consciente da spec:** o re-ACK da duplicata (SEQ == esperado−1) não está
> literal no enunciado ("fora de ordem = descarta em silêncio"), mas sem ele o
> stop-and-wait entra em deadlock quando um ACK se perde — justamente os cenários
> P1–P4 obrigatórios. É a correção padrão do rdt (Kurose).

### Encerramento (2 vias)
- Após o último ACK de dados, sender → FIN (`Length=0`); aguarda FIN+ACK (retransmite em timeout); fecha.
- Receiver, ao receber FIN → FIN+ACK e encerra.

## Endereçamento e portas
- Receiver (`--listen`) escuta na porta **P** (um socket fixo).
- Sender usa um socket fixo na porta **P+1**, envia tudo para `(host, P)` e recebe ACKs/SYN+ACK em P+1.
- Receiver sempre responde para o endereço de origem do pacote recebido (que é P+1), satisfazendo "ACKs vão para P+1" e maximizando interoperabilidade.

## CLI
```
# Receiver
python srtp.py --listen --port 6000 [--out received.bin] [--mode saw]

# Sender
python srtp.py --host 192.168.1.10 --port 6000 --file arquivo.bin [--mode saw]
```
- `--mode` aceita `saw` (default). `gbn`/`sr` ficam para a Parte 2.
- Timeout fixo: 100 ms. Payload: 255 bytes.

## Estatísticas (para o relatório)
Ao final, cada lado imprime: bytes transferidos, tempo decorrido, throughput (bits/s)
e número de retransmissões. Alimenta diretamente os itens de throughput medido e
contagem de retransmissões do relatório.

## Testes
- Unitários em `packet.py`: round-trip de encode/decode, CRC válido/inválido,
  empacotamento correto dos campos de 14 bits, wrap-around.
- Ponta a ponta local: transferir um arquivo > 50 pacotes e conferir que o hash
  bate com o original.
```
