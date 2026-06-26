# Relatório — SRTP (Trabalho Final, Lab. de Redes)

**Integrantes:** _(nomes)_
**Data:** _(preencher)_

> Protocolo de transporte confiável sobre UDP. As medições oficiais são entre duas
> máquinas distintas, com latência/perda/reordenação injetadas pelo *clumsy* e
> tráfego capturado no Wireshark (`.pcapng`). As células marcadas `<medir>` são
> preenchidas com esses dados reais.

---

## Parte 1 — Stop-and-Wait

### 1. Visão geral da implementação

O SRTP roda sobre UDP e adiciona confiabilidade na camada de aplicação. Cada
pacote leva um **cabeçalho de 9 bytes, big-endian**, com este layout:

| Campo | Bits | Função |
|---|---|---|
| SYN | 1 | abre conexão (handshake) |
| FIN | 1 | encerra conexão |
| SEQ | 14 | número de sequência (0..16383) |
| ACKflag | 1 | marca que o pacote é um ACK |
| NACK | 1 | marca que o pacote é um NACK |
| ACK | 14 | número confirmado / esperado / faltante |
| Length | 8 | comprimento útil do payload (ver semântica) |
| CRC32 | 32 | soma de verificação |

Os quatro primeiros campos ocupam uma palavra de 32 bits; seguem o byte de
*Length* e os 4 bytes de CRC32.

**CRC32.** É calculado com `zlib.crc32` sobre o cabeçalho **com o campo CRC
zerado** concatenado com o payload. No receptor o cálculo é refeito da mesma
forma; se não bate, o pacote está corrompido. Isso protege cabeçalho e dados.

**Semântica do Length (8 bits, máx 255).** Como o campo só vai até 255, ele
codifica a posição do pacote no fluxo: **255** = pacote intermediário (payload
cheio, vem mais coisa); **valor < 255** = último pacote (payload parcial); **0**
= caso de borda em que o arquivo é múltiplo exato do payload, sinalizando que o
último bloco cheio já foi enviado e a transferência terminou.

**Handshake de 3 vias.** SYN → SYN+ACK → ACK. Cada lado anuncia sua janela no
campo apropriado e a janela efetiva é o **mínimo** entre as duas, garantindo que
nenhum lado seja sobrecarregado. No stop-and-wait a janela é 1.

**Encerramento de 2 vias.** Após o último dado, o emissor manda **FIN** e o
receptor responde **FIN+ACK**, fechando a conexão de forma ordenada.

**Timeout fixo de 100 ms.** O emissor arma um temporizador de 100 ms ao enviar.
Se o ACK não chega nesse prazo, retransmite. O valor é fixo (não adaptativo),
o que é central para entender o comportamento nos cenários de latência.

**Portas P / P+1.** O serviço usa duas portas adjacentes (P e P+1), uma para
cada sentido lógico do canal.

### 2. Throughput teórico vs medido (cenário L0/P0)

Modelo de eficiência do ARQ stop-and-wait (Kurose & Ross, seção 3.4). Tamanhos
do pacote de dados cheio:

- `L_wire = (9+255)·8 = 2112 bits` (pacote no fio)
- `L_pay  = 255·8 = 2040 bits` (payload útil)
- `R` = taxa do enlace (bits/s). **Premissa:** _(declarar; ex.: LAN ~1 Gbps)_
- `t_trans = L_wire / R` (tempo de transmissão de 1 pacote)
- `RTT = RTT_base + 2 × latência_adicionada` (o clumsy adiciona a latência em cada sentido, portanto o round-trip recebe 2× a latência configurada por cenário)

Eficiência e goodput:

- `U_sw = t_trans / (RTT + t_trans)`
- `G_sw = L_pay / (RTT + t_trans)`

No stop-and-wait o emissor fica ocioso o RTT inteiro esperando o ACK antes de
mandar o próximo pacote. Por isso a utilização cai bruscamente quando o RTT
domina o `t_trans`.

| Grandeza | Símbolo | Valor |
|---|---|---|
| Tamanho no fio | `L_wire` | 2112 bits |
| Payload útil | `L_pay` | 2040 bits |
| Taxa do enlace | `R` | `<medir>` bits/s |
| Tempo de transmissão | `t_trans = L_wire/R` | `<calcular>` s |
| RTT | `RTT` | `<medir>` s |
| Utilização | `U_sw = t_trans/(RTT+t_trans)` | `<calcular>` |
| Goodput teórico | `G_sw = L_pay/(RTT+t_trans)` | `<calcular>` bits/s |

| Comparação | Goodput |
|---|---|
| Teórico `G_sw` | `<calcular>` bits/s |
| Medido (L0/P0) | `<medir>` bits/s |

**Sob perda `p`.** Cada pacote precisa em média `1/(1-p)` transmissões para
passar, então a fração de tempo gasta com dados que de fato avançam é `(1-p)`.
Logo `G_sw_perda ≈ G_sw·(1-p)` (aproximação).

### 3. Cenários de latência L0–L3

Latência adicionada por sentido: L0=0, L1=50, L2=100, L3=150 ms.

| Cenário | Latência (ms) | Throughput medido | Nº retransmissões |
|---|---|---|---|
| L0 | 0 | `<medir>` | `<medir>` |
| L1 | 50 | `<medir>` | `<medir>` |
| L2 | 100 | `<medir>` | `<medir>` |
| L3 | 150 | `<medir>` | `<medir>` |

**Comportamento em torno do timeout de 100 ms.** O RTT é cerca de duas vezes a
latência por sentido. Em **L1 (50 ms)** o RTT (~100 ms) já encosta no timeout:
o ACK chega no limite, então surgem as primeiras retransmissões espúrias quando
ele atrasa um pouco. Na transição **L1→L2 (100 ms)** o RTT (~200 ms) passa a
ultrapassar o timeout de forma sistemática: o emissor retransmite **antes** de o
ACK original chegar, pois ele ainda está a caminho. Isso gera tráfego duplicado
e derruba o throughput. Em **L2→L3 (150 ms)** o efeito se agrava: cada pacote
tende a ser enviado mais de uma vez, e o canal carrega cópias inúteis. A causa
raiz é o **timeout fixo**: ele não acompanha o aumento do RTT, então passa a
disparar cedo demais. Evidência nas capturas `saw_L1.pcapng` … `saw_L3.pcapng`
(comparar o instante do ACK com o da retransmissão).

### 4. Cenários de perda P0–P4

Perda: P0=0, P1=1, P2=5, P3=10, P4=25 %.

| Cenário | Perda (%) | Throughput medido | Nº retransmissões |
|---|---|---|---|
| P0 | 0 | `<medir>` | `<medir>` |
| P1 | 1 | `<medir>` | `<medir>` |
| P2 | 5 | `<medir>` | `<medir>` |
| P3 | 10 | `<medir>` | `<medir>` |
| P4 | 25 | `<medir>` | `<medir>` |

**Por que a perda reduz o throughput.** No stop-and-wait, um pacote (ou seu ACK)
perdido só é recuperado pelo timeout: o emissor espera 100 ms ociosos e
retransmite. Cada perda custa um ciclo inteiro de espera. Como em média são
`1/(1-p)` transmissões por pacote, o goodput segue `G_sw·(1-p)` — confronte a
coluna medida com esse valor. Com `p` crescendo (P4=25 %), além da retransmissão
mais frequente, o custo de cada timeout domina o tempo total.

### 5. Comportamento do CRC32

Quando um pacote chega corrompido, o CRC recalculado não bate com o transmitido.
O receptor **descarta o pacote silenciosamente** (não envia NACK): para o emissor
é indistinguível de uma perda, e o timeout cuida da retransmissão. Esse caminho
mantém o mecanismo simples — corrupção e perda convergem para a mesma
recuperação. Evidência: `saw_crc.pcapng` mostra o pacote corrompido recebido sem
ACK correspondente, seguido da retransmissão por timeout.

**Sem o CRC32**, dados corrompidos seriam aceitos como válidos e entregues à
aplicação sem nenhuma detecção, quebrando a integridade do arquivo. O CRC é o que
distingue "byte certo" de "byte parecido".

---

## Parte 2 — Go-Back-N e Selective Repeat

### 1. Visão geral

Ambos usam **o mesmo cabeçalho, handshake e encerramento da Parte 1**, mudando só
a política de janela e de recepção. A janela máxima é **255** (limite do campo
Length de 8 bits).

**Go-Back-N (GBN).** Janela de N pacotes em voo. O **receptor só aceita em
ordem**: qualquer pacote fora de ordem é descartado. O ACK é **cumulativo**
(confirma "recebi tudo até X"). Ao detectar buraco, o receptor manda **NACK com o
número esperado**. O emissor, ao expirar o timeout ou receber NACK, **retransmite
todos os pacotes a partir do primeiro não confirmado**.

**Selective Repeat (SR).** Janela de N pacotes em voo. O **receptor bufferiza
pacotes fora de ordem** e os entrega em ordem assim que a lacuna é preenchida. O
ACK é **individual** (confirma cada seq). O NACK carrega **o seq exatamente
faltante**, e o emissor **retransmite só esse pacote**.

A diferença de mecanismo (retransmitir o lote vs. só o faltante) é o que governa
o desempenho sob perda e reordenação.

### 2. Throughput teórico vs medido (GBN e SR)

Modelo de janela deslizante (mesmos `L_wire`, `L_pay`, `R`, `t_trans`, `RTT`):

- `U_win = min(1, N·t_trans / (RTT + t_trans))`
- `G_win = min( R·L_pay/L_wire , N·L_pay/(RTT + t_trans) )`

Com N pacotes em voo por RTT, a utilização cresce ~N vezes em relação ao
stop-and-wait, até saturar o enlace (`min` com `R·L_pay/L_wire`). É por isso que
uma janela suficiente esconde o RTT.

| Protocolo | Janela | `G_win` teórico | Medido |
|---|---|---|---|
| GBN | 4 | `<calcular>` | `<medir>` |
| GBN | 16 | `<calcular>` | `<medir>` |
| SR | 4 | `<calcular>` | `<medir>` |
| SR | 16 | `<calcular>` | `<medir>` |

(Em L0/P0, GBN e SR têm o mesmo teórico para uma dada janela; divergem sob
perda/reordenação.)

### 3. Comparativo sob latência (saw vs GBN vs SR, L0–L3)

| Cenário | Latência (ms) | saw | GBN | SR |
|---|---|---|---|---|
| L0 | 0 | `<medir>` | `<medir>` | `<medir>` |
| L1 | 50 | `<medir>` | `<medir>` | `<medir>` |
| L2 | 100 | `<medir>` | `<medir>` | `<medir>` |
| L3 | 150 | `<medir>` | `<medir>` | `<medir>` |

**Por que a janela mitiga a latência.** No stop-and-wait, um único pacote por RTT
significa que aumentar a latência multiplica o tempo ocioso. Com janela N, o
emissor envia até N pacotes **antes** de precisar de qualquer ACK, mantendo o
canal cheio durante o RTT. O throughput só cai quando N pacotes não bastam para
cobrir o tempo de ida e volta. Por isso GBN e SR seguram a vazão em L1–L3 muito
melhor que o saw, e janela 16 sustenta latências mais altas que janela 4.

### 4. Comparativo sob perda (GBN vs SR, P1–P4)

| Cenário | Perda (%) | GBN retransm. | SR retransm. | GBN throughput | SR throughput |
|---|---|---|---|---|---|
| P1 | 1 | `<medir>` | `<medir>` | `<medir>` | `<medir>` |
| P2 | 5 | `<medir>` | `<medir>` | `<medir>` | `<medir>` |
| P3 | 10 | `<medir>` | `<medir>` | `<medir>` | `<medir>` |
| P4 | 25 | `<medir>` | `<medir>` | `<medir>` | `<medir>` |

**Diferença de mecanismo.** Quando um pacote se perde, o **GBN retransmite todo o
lote** a partir do não confirmado, mesmo que os pacotes seguintes tenham chegado
bem — eles foram descartados pelo receptor por estarem fora de ordem. O **SR
retransmite só o pacote faltante**, pois o receptor guardou os demais no buffer.
Por isso, sob perda, o GBN gera muito mais retransmissões (e o efeito piora com
janela maior, ver seção 6), enquanto o SR mantém o número de retransmissões perto
do número de perdas. **SR é mais eficiente sob perda** justamente porque não
joga fora trabalho já feito.

### 5. Comparativo sob reordenação R0–R2 (ponto central)

Reordenação: R0=0, R1=10, R2=25 %.

| Cenário | Reord. (%) | GBN retransm. | SR retransm. | GBN throughput | SR throughput |
|---|---|---|---|---|---|
| R0 | 0 | `<medir>` | `<medir>` | `<medir>` | `<medir>` |
| R1 | 10 | `<medir>` | `<medir>` | `<medir>` | `<medir>` |
| R2 | 25 | `<medir>` | `<medir>` | `<medir>` | `<medir>` |

**Contraste de comportamento.** A reordenação não perde pacotes, só os entrega
fora de ordem — e é aqui que os dois protocolos divergem de forma marcante.

No **GBN**, um pacote que chega adiantado (fora de ordem) é **descartado**, pois o
receptor só aceita em ordem. Ele responde com **NACK do esperado**, e o emissor
**retransmite o lote**. Ou seja, o GBN trata reordenação quase como perda:
desperdiça os pacotes que na verdade já tinham chegado, gerando retransmissão em
lote e derrubando o throughput. Evidência: `gbn_R2_janela16.pcapng` mostra o
descarte do fora de ordem, o NACK e a rajada de retransmissões.

No **SR**, o pacote fora de ordem é **bufferizado** dentro da janela; quando o
pacote que faltava chega, o receptor **entrega tudo em ordem** a partir do buffer —
e nunca descarta pacotes já recebidos. Esse buffer é a vantagem do SR sobre o GBN.
Ainda assim, ao detectar a lacuna o receptor envia um **NACK com o número de
sequência do pacote faltante**, e o emissor **retransmite apenas aquele pacote**.
Sob reordenação pura (sem perda) o pacote faltante está só atrasado e chega logo
em seguida, então o NACK pode disparar uma **retransmissão espúria** (o pacote
acaba chegando duas vezes: o original reordenado mais o retransmitido). Ou seja, o
SR também gera **alguma** retransmissão sob reordenação, mas é de um único pacote e
sem desperdiçar o que já chegou. Evidência: `sr_R2_janela16.pcapng` mostra a
bufferização, o NACK do pacote faltante e a retransmissão pontual.

Conclusão da seção: **o SR lida com reordenação melhor que o GBN** — bufferiza e
entrega em ordem em vez de descartar e retransmitir o lote. O SR ainda incorre em
retransmissão de um pacote por NACK, mas muito menos custosa que a rajada do GBN, e
isso aparece direto na coluna de retransmissões.

### 6. Impacto do tamanho de janela (4 vs 16)

| Protocolo | Janela | Throughput | Retransmissões |
|---|---|---|---|
| GBN | 4 | `<medir>` | `<medir>` |
| GBN | 16 | `<medir>` | `<medir>` |
| SR | 4 | `<medir>` | `<medir>` |
| SR | 16 | `<medir>` | `<medir>` |

**Trade-off.** Janela maior aumenta o throughput potencial (mais pacotes em voo
por RTT, melhor uso do enlace), e em canal limpo 16 vence 4 com folga. Porém, no
**GBN sob perda ou reordenação**, a janela maior aumenta o **custo de cada
retransmissão em lote**: ao reenviar a partir do não confirmado, há mais pacotes
para reenviar, então o ganho de vazão pode ser anulado pelo trabalho repetido. No
**SR**, janela maior é quase sempre benéfica, pois a retransmissão é pontual e não
cresce com N. Daí a regra prática: aumente a janela livremente no SR; no GBN, pese
o ganho contra a taxa de perda/reordenação esperada.

### 7. Conclusão comparativa

A escolha do protocolo depende das condições do enlace, e os dados medidos acima
sustentam a recomendação:

- **Canal limpo, baixa latência:** os três entregam bem; o stop-and-wait basta e é
  o mais simples. _(confrontar L0/P0)_
- **Latência alta, pouca perda:** janela deslizante é essencial — saw colapsa com o
  RTT, GBN e SR seguram a vazão. Entre os dois, empatam aqui; preferir o mais
  simples (GBN). _(confrontar L2/L3)_
- **Perda significativa:** **SR** vence claramente — retransmite só o faltante,
  enquanto o GBN reenvia o lote. _(confrontar P3/P4 na seção 4)_
- **Reordenação significativa:** **SR** é a única escolha sensata — o GBN trata
  reordenação como perda e desperdiça retransmissões. _(confrontar R2 na seção 5)_

Em resumo: **stop-and-wait** para enlaces curtos e limpos; **GBN** quando a
latência é o problema e a perda é baixa (mais simples que o SR); **SR** quando há
perda ou reordenação relevantes, pois é o único que não desperdiça trabalho já
feito. Os números medidos confirmam que a vantagem do SR cresce exatamente nos
cenários P4 e R2. _(finalizar citando os valores obtidos)_
