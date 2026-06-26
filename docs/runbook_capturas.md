# Runbook de Capturas — SRTP (clumsy + Wireshark)

Guia passo a passo para gerar TODOS os `.pcapng` obrigatorios do trabalho. As
medicoes oficiais sao entre **duas maquinas distintas** na mesma LAN, com o
`clumsy` injetando latencia/perda/reordenacao e o Wireshark gravando.

> Nomeie os arquivos EXATAMENTE como neste runbook. Nome trocado perde ponto.

---

## 1. Setup

1. Duas maquinas na mesma rede local (mesma LAN/switch/Wi-Fi).
   - **Maquina R (receiver)** e **maquina S (sender)**.
2. Descubra o IP da maquina R (receiver):
   - Windows: `ipconfig` (campo "Endereco IPv4", ex.: `192.168.1.10`).
   - Linux: `ip addr` ou `hostname -I`.
   - Anote como `<IP_RECEIVER>`. Confirme com `ping <IP_RECEIVER>` a partir de S.
3. Escolha uma porta base `P`. Use **`P = 6000`** em todo o runbook.
   - O sender envia dados para `P` e escuta ACKs em `P+1` (6001). Libere ambas
     no firewall se necessario.

### Arquivo de teste (>= 50 pacotes de dados)

Payload util por pacote = 255 bytes. Para gerar **>= 50 pacotes** o arquivo
precisa de ~13 KB. Use um arquivo de **~64 KB** (gera ~255 pacotes), chamado
`teste.bin`.

- Windows (PowerShell):
  ```powershell
  $bytes = New-Object byte[] 65536
  (New-Object Random).NextBytes($bytes)
  [IO.File]::WriteAllBytes("teste.bin", $bytes)
  ```
- Linux:
  ```bash
  head -c 65536 /dev/urandom > teste.bin
  ```

Copie `teste.bin` para a maquina S (sender). A maquina R grava em
`recebido.bin`. Ao final, confira integridade (devem bater):

```powershell
Get-FileHash teste.bin, recebido.bin -Algorithm SHA256   # Windows
```
```bash
sha256sum teste.bin recebido.bin                          # Linux
```

---

## 2. clumsy (Windows) — uma instancia por captura

O `clumsy` roda em **UMA** das maquinas (sender OU receiver), conforme a spec
("clumsy no sender ou receiver"). Rode na maquina Windows que estiver no
caminho. Em todas as funcoes, ative tambem **Inbound** e **Outbound** e use o
filtro para nao afetar trafego alheio:

```
Filtering: udp and (udp.DstPort == 6000 or udp.SrcPort == 6000 or udp.DstPort == 6001 or udp.SrcPort == 6001)
```

Marque o checkbox da funcao, ajuste o parametro, clique **Start** antes da
transferencia, **Stop** ao terminar. Use UMA funcao por cenario (nao combine).

### Latencia (funcao Lag) — cenarios L

| Cenario | Lag (ms) | Demais funcoes |
|---|---|---|
| L0 | 0 (clumsy desligado) | nenhuma |
| L1 | 50 | so Lag |
| L2 | 100 | so Lag |
| L3 | 150 | so Lag |

### Perda (funcao Drop) — cenarios P

| Cenario | Drop (%) | Demais funcoes |
|---|---|---|
| P0 | 0 (clumsy desligado) | nenhuma |
| P1 | 1 | so Drop |
| P2 | 5 | so Drop |
| P3 | 10 | so Drop |
| P4 | 25 | so Drop |

### Reordenacao (funcao Out of order) — cenarios R (Parte 2)

| Cenario | Out of order (%) | Demais funcoes |
|---|---|---|
| R0 | 0 (clumsy desligado) | nenhuma |
| R1 | 10 | so Out of order |
| R2 | 25 | so Out of order |

> L0, P0 e R0 sao a baseline limpa: clumsy parado (ou sem funcao marcada).

---

## 3. Wireshark — iniciar e salvar

1. Abra o Wireshark na maquina que ve o trafego (normalmente a R, ou a que
   roda o clumsy). Escolha a interface da LAN (a do `<IP_RECEIVER>`).
2. Filtro de captura/exibicao para isolar o trafego SRTP:
   ```
   udp.port == 6000 || udp.port == 6001
   ```
3. Clique no tubarao azul para **iniciar** a captura ANTES de rodar os comandos.
4. Rode o par de comandos do cenario (secao 4).
5. Apos o sender terminar (imprime "enviados N bytes"), clique no quadrado
   vermelho para **parar**.
6. **File > Save As** > formato **pcapng** > nome exato do cenario (ex.:
   `saw_L2.pcapng`). Salve em `capturas/`.

---

## 4. Matriz de cenarios — comandos exatos

Em todos os pares: **inicie o receiver primeiro**, depois o sender. Ajuste o
clumsy (secao 2) e a captura (secao 3) antes de disparar o sender.

`<IP_RECEIVER>` = IP da maquina R. Porta `P = 6000`.

### Parte 1 — stop-and-wait (`saw`)

Para cada cenario abaixo:
```bash
# Receiver (maquina R)
python srtp.py --listen --port 6000 --mode saw --out recebido.bin

# Sender (maquina S)
python srtp.py --host <IP_RECEIVER> --port 6000 --mode saw --file teste.bin
```

| Cenario | clumsy | Arquivo |
|---|---|---|
| L0 | nenhum | `saw_L0.pcapng` |
| L1 | Lag 50 ms | `saw_L1.pcapng` |
| L2 | Lag 100 ms | `saw_L2.pcapng` |
| L3 | Lag 150 ms | `saw_L3.pcapng` |
| P0 | nenhum | `saw_P0.pcapng` |
| P1 | Drop 1% | `saw_P1.pcapng` |
| P2 | Drop 5% | `saw_P2.pcapng` |
| P3 | Drop 10% | `saw_P3.pcapng` |
| P4 | Drop 25% | `saw_P4.pcapng` |

### Parte 2 — Go-Back-N (`gbn`) e Selective Repeat (`sr`)

Repita L0-L3, P0-P4 **e** R0-R2 para os DOIS modos, **cada um com janela 4 e
janela 16**. Padrao de nome: `<modo>_<cenario>_janela<N>.pcapng`.

Comando (troque `<modo>` por `gbn`/`sr` e `<N>` por `4`/`16`):
```bash
# Receiver (maquina R)
python srtp.py --listen --port 6000 --mode <modo> --window <N> --out recebido.bin

# Sender (maquina S)
python srtp.py --host <IP_RECEIVER> --port 6000 --mode <modo> --window <N> --file teste.bin
```

Exemplos concretos:
```bash
python srtp.py --listen --port 6000 --mode gbn --window 16 --out recebido.bin
python srtp.py --host <IP_RECEIVER> --port 6000 --mode gbn --window 16 --file teste.bin
```

**Go-Back-N, janela 4** (clumsy igual a Parte 1; R = Out of order):
`gbn_L0_janela4.pcapng`, `gbn_L1_janela4.pcapng`, `gbn_L2_janela4.pcapng`,
`gbn_L3_janela4.pcapng`, `gbn_P0_janela4.pcapng`, `gbn_P1_janela4.pcapng`,
`gbn_P2_janela4.pcapng`, `gbn_P3_janela4.pcapng`, `gbn_P4_janela4.pcapng`,
`gbn_R0_janela4.pcapng`, `gbn_R1_janela4.pcapng`, `gbn_R2_janela4.pcapng`.

**Go-Back-N, janela 16**:
`gbn_L0_janela16.pcapng`, `gbn_L1_janela16.pcapng`, `gbn_L2_janela16.pcapng`,
`gbn_L3_janela16.pcapng`, `gbn_P0_janela16.pcapng`, `gbn_P1_janela16.pcapng`,
`gbn_P2_janela16.pcapng`, `gbn_P3_janela16.pcapng`, `gbn_P4_janela16.pcapng`,
`gbn_R0_janela16.pcapng`, `gbn_R1_janela16.pcapng`, `gbn_R2_janela16.pcapng`.

**Selective Repeat, janela 4**:
`sr_L0_janela4.pcapng`, `sr_L1_janela4.pcapng`, `sr_L2_janela4.pcapng`,
`sr_L3_janela4.pcapng`, `sr_P0_janela4.pcapng`, `sr_P1_janela4.pcapng`,
`sr_P2_janela4.pcapng`, `sr_P3_janela4.pcapng`, `sr_P4_janela4.pcapng`,
`sr_R0_janela4.pcapng`, `sr_R1_janela4.pcapng`, `sr_R2_janela4.pcapng`.

**Selective Repeat, janela 16**:
`sr_L0_janela16.pcapng`, `sr_L1_janela16.pcapng`, `sr_L2_janela16.pcapng`,
`sr_L3_janela16.pcapng`, `sr_P0_janela16.pcapng`, `sr_P1_janela16.pcapng`,
`sr_P2_janela16.pcapng`, `sr_P3_janela16.pcapng`, `sr_P4_janela16.pcapng`,
`sr_R0_janela16.pcapng`, `sr_R1_janela16.pcapng`, `sr_R2_janela16.pcapng`.

### Demonstracao do CRC32 (`saw_crc.pcapng`)

O clumsy nao corrompe payload, entao usamos o relay `corrupt.py` (raiz do
repo) no caminho. Ele vira um byte de UM pacote de dados: o CRC32 falha, o
receiver **descarta em silencio (sem NACK)** e o sender retransmite por
**timeout**. A captura deve mostrar: pacote de dados -> (sem ACK) -> timeout ->
retransmissao -> ACK.

Tres processos (clumsy DESLIGADO neste cenario). O `corrupt.py` pode rodar na
maquina R ou em uma terceira; aqui assumimos na propria maquina R:

A porta do receiver tem que ser exatamente uma a menos que o `--listen-port` do
relay, porque o receiver manda seus ACKs para P+1 (aqui 6001), que precisa ser a
porta de escuta do relay para ele repassar os ACKs de volta ao sender. Na mesma
maquina, rode receiver, relay e sender em tres terminais.

```bash
# 1) Receiver (maquina R), porta 6000 (ACKs vao para P+1 = 6001)
python srtp.py --listen --port 6000 --mode saw --out recebido.bin

# 2) Relay que corrompe 1 pacote (maquina R): escuta em 6001, repassa pro 6000
python corrupt.py --listen-port 6001 --target-host 127.0.0.1 --target-port 6000 --which 1

# 3) Sender (maquina S) aponta para o relay (IP da maquina R, porta 6001)
python srtp.py --host 127.0.0.1 --port 6001 --mode saw --file teste.bin
```

No Wireshark, capture na interface de loopback (se relay+receiver na mesma
maquina) ou filtre `udp.port == 6000 || udp.port == 6001 || udp.port == 6002`.
Salve como `saw_crc.pcapng`. O `corrupt.py` imprime a linha confirmando qual
pacote corrompeu.

---

## 5. Checklist final — todos os `.pcapng`

Marque cada um. Todos vao para `capturas/`.

### Parte 1 — saw (9)
- [ ] `saw_L0.pcapng`
- [ ] `saw_L1.pcapng`
- [ ] `saw_L2.pcapng`
- [ ] `saw_L3.pcapng`
- [ ] `saw_P0.pcapng`
- [ ] `saw_P1.pcapng`
- [ ] `saw_P2.pcapng`
- [ ] `saw_P3.pcapng`
- [ ] `saw_P4.pcapng`

### Parte 2 — gbn janela 4 (12)
- [ ] `gbn_L0_janela4.pcapng`
- [ ] `gbn_L1_janela4.pcapng`
- [ ] `gbn_L2_janela4.pcapng`
- [ ] `gbn_L3_janela4.pcapng`
- [ ] `gbn_P0_janela4.pcapng`
- [ ] `gbn_P1_janela4.pcapng`
- [ ] `gbn_P2_janela4.pcapng`
- [ ] `gbn_P3_janela4.pcapng`
- [ ] `gbn_P4_janela4.pcapng`
- [ ] `gbn_R0_janela4.pcapng`
- [ ] `gbn_R1_janela4.pcapng`
- [ ] `gbn_R2_janela4.pcapng`

### Parte 2 — gbn janela 16 (12)
- [ ] `gbn_L0_janela16.pcapng`
- [ ] `gbn_L1_janela16.pcapng`
- [ ] `gbn_L2_janela16.pcapng`
- [ ] `gbn_L3_janela16.pcapng`
- [ ] `gbn_P0_janela16.pcapng`
- [ ] `gbn_P1_janela16.pcapng`
- [ ] `gbn_P2_janela16.pcapng`
- [ ] `gbn_P3_janela16.pcapng`
- [ ] `gbn_P4_janela16.pcapng`
- [ ] `gbn_R0_janela16.pcapng`
- [ ] `gbn_R1_janela16.pcapng`
- [ ] `gbn_R2_janela16.pcapng`

### Parte 2 — sr janela 4 (12)
- [ ] `sr_L0_janela4.pcapng`
- [ ] `sr_L1_janela4.pcapng`
- [ ] `sr_L2_janela4.pcapng`
- [ ] `sr_L3_janela4.pcapng`
- [ ] `sr_P0_janela4.pcapng`
- [ ] `sr_P1_janela4.pcapng`
- [ ] `sr_P2_janela4.pcapng`
- [ ] `sr_P3_janela4.pcapng`
- [ ] `sr_P4_janela4.pcapng`
- [ ] `sr_R0_janela4.pcapng`
- [ ] `sr_R1_janela4.pcapng`
- [ ] `sr_R2_janela4.pcapng`

### Parte 2 — sr janela 16 (12)
- [ ] `sr_L0_janela16.pcapng`
- [ ] `sr_L1_janela16.pcapng`
- [ ] `sr_L2_janela16.pcapng`
- [ ] `sr_L3_janela16.pcapng`
- [ ] `sr_P0_janela16.pcapng`
- [ ] `sr_P1_janela16.pcapng`
- [ ] `sr_P2_janela16.pcapng`
- [ ] `sr_P3_janela16.pcapng`
- [ ] `sr_P4_janela16.pcapng`
- [ ] `sr_R0_janela16.pcapng`
- [ ] `sr_R1_janela16.pcapng`
- [ ] `sr_R2_janela16.pcapng`

### Demonstracao CRC32 (1)
- [ ] `saw_crc.pcapng`

**Total: 58 arquivos `.pcapng`.**
