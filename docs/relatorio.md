# Relatório — SRTP (Trabalho Final, Lab. de Redes)

> Esqueleto a preencher com os dados reais coletados no lab (2 máquinas distintas
> + clumsy + Wireshark). Limite: **5 páginas** no PDF final. Converter para PDF
> antes de entregar. As seções e pesos seguem o enunciado.

**Integrantes:** _(nomes)_
**Data:** _(preencher)_

---

## 1. Visão geral da implementação
- Linguagem: Python 3 (stdlib: `socket`, `struct`, `zlib`). Sem dependências.
- Cabeçalho de 9 bytes (SEQ 14b, SYN, FIN, ACK 14b, ACKflag, NACK, Length 8b, CRC32).
- Mesmo binário, três modos (`--mode saw|gbn|sr`); janela negociada no handshake
  (campo Length, máx 255); timeout fixo 100 ms.
- Formato de fio do controle (contrato de interop):
  - ACK: `ACKflag=1, NACK=0`, campo ACK = seq (cumulativo em gbn, individual em sr).
  - NACK: `NACK=1, ACKflag=0`, campo ACK = seq esperado (gbn) / faltante (sr).

## 2. Parte 1 — Stop-and-Wait

### 2.1 Throughput teórico vs medido (cenário L0/P0)  *(peso 7%)*
- Fórmula ARQ (Kurose & Ross §3.4): U = (L/R) / (RTT + L/R); vazão = U·R.
- Tabela: teórico vs medido em L0/P0. _(preencher com bench.py + captura real)_

### 2.2 Cenários de latência L0–L3  *(peso 7%)*
- Tabela: throughput medido e nº de retransmissões por cenário.
- Discutir a transição L1→L2→L3 em função do timeout de 100 ms (quando RTT+proc.
  ultrapassa 100 ms surgem retransmissões espúrias). Evidência: capturas.

### 2.3 Cenários de perda P0–P4  *(peso 6%)*
- Tabela: throughput e retransmissões. Relacionar com eficiência sob perda.

### 2.4 Comportamento do CRC32
- Captura mostrando pacote corrompido detectado e descartado (sem NACK).
- O que aconteceria sem CRC32: entrega de dados corrompidos como válidos.

## 3. Parte 2 — Go-Back-N e Selective Repeat

### 3.1 Throughput teórico vs medido (GBN e SR)  *(peso 5%)*
- Janela deslizante: vazão ≈ min(W·L/(RTT+L/R), R). Comparar teórico vs medido.

### 3.2 Comparativo sob latência e perda  *(peso 8%)*
- L0–L3: por que a janela deslizante reduz o impacto da latência (vários pacotes
  em trânsito por RTT).
- P1–P4: comparar nº de retransmissões GBN vs SR; GBN retransmite a janela inteira
  (mais retransmissões sob perda), SR só o pacote perdido.

### 3.3 Comparativo sob reordenação R0–R2  *(peso 10% — ponto central)*
- GBN: capturas devem mostrar descarte do fora de ordem + NACK(esperado) +
  retransmissão em lote.
- SR: capturas devem mostrar bufferização + ACK individual + NACK(faltante) +
  entrega em ordem ao preencher a lacuna.
- Explicar por que divergem: política de aceitação do receiver.

### 3.4 Impacto do tamanho de janela (4 vs 16)  *(dentro do peso comparativo)*
- Para cada protocolo: throughput e retransmissões com W=4 e W=16.
- Trade-off: janela maior = mais throughput potencial, mas no GBN sob perda =
  mais retransmissão em lote.

### 3.5 Conclusão comparativa  *(peso 7%)*
- Em que condição cada modo é melhor, **fundamentado nos dados medidos**.

---

## 4. Matriz de capturas obrigatórias (`capturas/`)

Nomear `<modo>_<cenario>[_janela<N>].pcapng`. Cada cenário ≥ 50 pacotes de dados.

**SAW** (sem reordenação; só latência e perda):
- `saw_L0` `saw_L1` `saw_L2` `saw_L3`
- `saw_P0` `saw_P1` `saw_P2` `saw_P3` `saw_P4`

**GBN** — para cada janela ∈ {4, 16}:
- `gbn_L0_janela4` … `gbn_L3_janela4`, idem `_janela16`
- `gbn_P0_janela4` … `gbn_P4_janela4`, idem `_janela16`
- `gbn_R0_janela4` `gbn_R1_janela4` `gbn_R2_janela4`, idem `_janela16`

**SR** — para cada janela ∈ {4, 16}:
- `sr_L0_janela4` … `sr_L3_janela4`, idem `_janela16`
- `sr_P0_janela4` … `sr_P4_janela4`, idem `_janela16`
- `sr_R0_janela4` `sr_R1_janela4` `sr_R2_janela4`, idem `_janela16`

Cenários: L0=0/L1=50/L2=100/L3=150 ms; P0=0/P1=1/P2=5/P3=10/P4=25 %;
R0=0/R1=10/R2=25 %. Latência/perda/reordenação via clumsy no sender OU receiver.

## 5. Teste de interoperabilidade
- Validar o formato de fio (seção 1) com o outro grupo ANTES do teste ao vivo —
  em especial: `ACKflag=0` no NACK e o valor cumulativo do ACK em GBN
  (maior seq recebido em ordem).
- Sucesso = hash do arquivo recebido idêntico ao original.
