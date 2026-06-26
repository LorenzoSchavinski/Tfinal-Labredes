# SRTP — Simple Reliable Transport Protocol (sobre UDP)

Implementação do trabalho final de Laboratório de Redes de Computadores.
**Parte 1: stop-and-wait. Parte 2: Go-Back-N e Selective Repeat.**
O mesmo binário suporta os três modos via `--mode {saw,gbn,sr}`.

## Requisitos

- Python 3.11+. Sem dependências externas — usa apenas a
  biblioteca padrão (`socket`, `struct`, `zlib`).

## Como executar

Não precisa compilar. Em duas máquinas distintas da rede local:

```bash
# 1) No receiver (escuta na porta P = 6000):
python srtp.py --listen --port 6000 --out recebido.bin --mode gbn --window 16

# 2) No sender (envia um arquivo para o receiver):
python srtp.py --host <IP_DO_RECEIVER> --port 6000 --file arquivo.bin --mode gbn --window 16
```

O sender envia os dados para a porta `P` e escuta ACKs na porta `P+1`.
Os dois lados devem usar o mesmo `--mode`. A janela efetiva da sessão é
`min(--window do sender, --window do receiver)`, negociada no handshake
(campo Length, máximo 255). Em `saw` a janela é sempre 1.

## Modos do protocolo

| Modo | Mecanismo | Receiver | Retransmissão | ACK | NACK |
|---|---|---|---|---|---|
| `saw` | stop-and-wait | aceita só o esperado | 1 pacote (timeout) | por pacote | — |
| `gbn` | Go-Back-N | aceita só em ordem | janela inteira a partir do não confirmado (timeout/NACK) | cumulativo: ACK(n) confirma até n | flag NACK + campo ACK = seq esperado |
| `sr` | Selective Repeat | bufferiza fora de ordem | só o não confirmado (timeout/NACK) | individual: ACK(n) confirma só n | flag NACK + campo ACK = seq faltante |

**Formato de fio do controle** (contrato para interoperabilidade):
- ACK positivo: `ACK flag = 1`, `NACK = 0`, campo ACK = número de sequência.
- NACK: `NACK = 1`, `ACK flag = 0`, campo ACK = seq esperado (GBN) / faltante (SR).

## Medição local (relatório)

`bench.py` roda transferências localmente com latência/perda/reordenação simuladas
e imprime throughput medido vs teórico e retransmissões:

```bash
python bench.py                                   # tabela dos modos (limpo)
python bench.py --mode gbn --window 16 --latency 0.05
python bench.py --mode sr  --window 4  --loss 10
```

> As medições OFICIAIS do trabalho são entre duas máquinas distintas, com o
> `clumsy` injetando latência/perda/reordenação e o Wireshark gravando `.pcapng`.
> O `bench.py` é apenas para sanity-check e tendências locais.

## Argumentos de linha de comando

| Argumento | Modo | Descrição |
|---|---|---|
| `--listen` | receiver | Ativa o modo receiver (escuta na porta P). |
| `--host IP` | sender | IP do receiver. |
| `--port P` | ambos | Porta base P (sender usa P+1 para receber ACKs). |
| `--file caminho` | sender | Arquivo a transferir. |
| `--out caminho` | receiver | Arquivo de saída (default: `received.bin`). |
| `--mode saw\|gbn\|sr` | ambos | Modo do protocolo (default: `saw`). |
| `--window N` | ambos | Janela proposta no handshake, 1–255 (default: 1). |

Ao final, cada lado imprime bytes transferidos, tempo, throughput e número de
retransmissões — útil para o relatório.

## Estrutura do código

| Arquivo | Responsabilidade |
|---|---|
| `packet.py` | Cabeçalho RTP de 9 bytes: montagem, leitura e CRC32. |
| `sender.py` | Sender: handshake, transferência (saw/gbn/sr), FIN. |
| `receiver.py` | Receiver: handshake, recepção (saw/gbn/sr), FIN. |
| `srtp.py` | CLI: lê argumentos e chama sender ou receiver. |
| `bench.py` | Harness de medição local (throughput/retransmissões). |
| `test_packet.py` | Testes unitários do cabeçalho/CRC. |
| `test_e2e.py` | Transferência ponta a ponta (saw). |
| `test_loss.py` | Transferência saw sob perda (proxy UDP). |
| `test_modes.py` | GBN e SR: limpo, perda e reordenação (janelas 4 e 16). |

## Testes

```bash
python -m unittest                # roda todos
python -m unittest test_modes -v  # só GBN/SR
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

## Empacotamento da entrega

O zip da entrega contem **apenas** o necessario:

- Fontes `.py` (`srtp.py`, `packet.py`, `sender.py`, `receiver.py`, `corrupt.py`,
  `bench.py`, os `test_*.py`).
- `README.md` e o relatorio exportado em `docs/relatorio.pdf`.
- `capturas/` com todos os `.pcapng`.

E **exclui**: binarios/dados de teste (`*.bin`, `received.bin`, `teste.bin`,
`recebido.bin`), `__pycache__/`, o PDF do enunciado (`T2_20261.pdf`), os rascunhos
em markdown (`docs/runbook_capturas.md`, `docs/relatorio.md`) e a pasta
`docs/superpowers/` (notas internas de processo — nao fazem parte da entrega).

> Antes de zipar, exporte `docs/relatorio.md` para PDF como `docs/relatorio.pdf`
> (no maximo 5 paginas).

Para montar o zip apenas com o conteudo exigido (PowerShell, na raiz do repo).
Os arquivos sao copiados para uma pasta temporaria antes de zipar, garantindo que
`docs/superpowers/` e os rascunhos em markdown nao vazem para a entrega:

```powershell
$fontes = @(
  'srtp.py','packet.py','sender.py','receiver.py','corrupt.py','bench.py',
  'test_packet.py','test_e2e.py','test_loss.py','test_modes.py',
  'README.md'
)
$stage = Join-Path $env:TEMP 'entrega_srtp'
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage | Out-Null

Copy-Item $fontes -Destination $stage
New-Item -ItemType Directory -Path (Join-Path $stage 'docs') | Out-Null
Copy-Item 'docs/relatorio.pdf' -Destination (Join-Path $stage 'docs')
Copy-Item 'capturas' -Destination $stage -Recurse -Filter '*.pcapng'

Compress-Archive -Path (Join-Path $stage '*') -DestinationPath entrega_srtp.zip -Force
Remove-Item $stage -Recurse -Force
```
