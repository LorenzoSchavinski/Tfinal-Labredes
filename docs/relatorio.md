# Relatório — SRTP (Trabalho Final, Lab. de Redes)

**Integrantes:** _(nomes)_
**Data:** _(preencher)_

---

## Parte 1 — Stop-and-Wait

### 1. Visão geral da implementação

O SRTP roda sobre UDP e adiciona confiabilidade na aplicação. Cada pacote tem um cabeçalho de 9 bytes big-endian (SYN, FIN, SEQ de 14 bits, ACKflag, NACK, ACK de 14 bits, Length de 8 bits e CRC32 de 32 bits). O Length codifica a posição no fluxo: 255 = payload cheio e ainda vem mais, valor < 255 = último pacote, 0 = arquivo múltiplo exato do payload e o último bloco cheio já foi enviado. O CRC32 é calculado com `zlib.crc32` sobre o cabeçalho (com o campo CRC zerado) mais o payload, protegendo cabeçalho e dados. A conexão abre por handshake de 3 vias (SYN → SYN+ACK → ACK, cada lado anuncia sua janela e a efetiva é o mínimo entre as duas) e fecha por FIN/FIN+ACK. O timeout é fixo em 100 ms, e no stop-and-wait a janela é 1. O serviço usa duas portas adjacentes (P e P+1), uma por sentido.

### 2. Throughput teórico vs medido (cenário L0/P0)

Pra comparar com o medido usei a fórmula de stop-and-wait do Kurose (`G_sw = L_pay/(RTT+t_trans)`). O payload é 255 B (2040 bits) e o pacote no fio 264 B (2112 bits). No cabo Gigabit o tempo de transmissão dá ~2,1 µs, desprezível perto do RTT base (~0,72 ms), então a vazão fica limitada pelo RTT. Com isso o teórico em L0 dá ~2833 kbit/s, e a gente mediu 2847,3 kbit/s. Pra perda usei `G_sw·(1-p)`, mas é um teto otimista porque não conta o tempo parado esperando o timeout.

### 3. Cenários de latência L0–L3

Latência adicionada por sentido: L0=0, L1=50, L2=100, L3=150 ms.

| Cenário | Latência (ms) | RTT≈ (ms) | Throughput medido (kbit/s) | Nº retransmissões | Teórico (kbit/s) |
|---|---|---|---|---|---|
| L0 | 0 | 0,72 | 2847,3 | 0 | 2833 |
| L1 | 50 | 100,7 | 12,6 | 147 | 20,3 |
| L2 | 100 | 200,7 | 9,2 | 390 | 10,2 |
| L3 | 150 | 300,7 | 6,3 | 504 | 6,8 |

O RTT é mais ou menos 2× a latência por sentido. Em L1 (~100 ms) ele já encosta no timeout de 100 ms e começam as retransmissões desnecessárias (147), derrubando a vazão. De L1 pra L2 (~200 ms) o RTT passa do timeout: o emissor reenvia antes do ACK voltar (390), e L3 piora (504). Como o timeout é fixo, ele dispara cedo demais e o medido fica abaixo do teórico (ver `saw_L1.pcapng` a `saw_L3.pcapng`).

### 4. Cenários de perda P0–P4

Perda: P0=0, P1=1, P2=5, P3=10, P4=25 %.

| Cenário | Perda (%) | Throughput medido (kbit/s) | Nº retransmissões | Teórico `G_sw·(1-p)` (kbit/s) |
|---|---|---|---|---|
| P0 | 0 | 3176,8 | 0 | 2833 |
| P1 | 1 | 553,4 | 6 | 2805 |
| P2 | 5 | 109,0 | 41 | 2691 |
| P3 | 10 | 67,2 | 68 | 2550 |
| P4 | 25 | 17,7 | 263 | 2125 |

A perda derruba a vazão porque cada pacote perdido custa um timeout inteiro de 100 ms parado, não só o reenvio. Por isso o medido (553→17 kbit/s) cai muito mais que o teórico `G_sw·(1-p)` (2805→2125 kbit/s), que assume reenvio na hora. As retransmissões sobem com a taxa de perda (6→263), como aparece em `saw_P2.pcapng` e `saw_P4.pcapng`. (L0 e P0 são o mesmo enlace limpo; a diferença entre 2847 e 3177 kbit/s é só jitter da LAN.)

### 5. Comportamento do CRC32

Pacote com CRC32 inválido é descartado em silêncio, sem NACK, e o timeout do emissor retransmite — vira o mesmo caminho de uma perda. Na captura `saw_crc.pcapng` dá pra ver o pacote corrompido sem ACK e a retransmissão depois. Sem o CRC, esse pacote seria entregue à aplicação como válido e corromperia o arquivo sem ninguém perceber.

---

## Parte 2 — Go-Back-N e Selective Repeat

### 1. Visão geral

GBN e SR usam o mesmo cabeçalho, handshake e encerramento da Parte 1, mudando só a política de janela e recepção (janela máxima 255, limite do campo Length).

- **Go-Back-N:** janela de N em voo, receptor só aceita em ordem (fora de ordem é descartado), ACK cumulativo e NACK do esperado. No timeout ou NACK, retransmite todos a partir do primeiro não confirmado.
- **Selective Repeat:** janela de N em voo, receptor bufferiza os fora de ordem e entrega quando a lacuna fecha, ACK individual e NACK do seq faltante. Retransmite só esse pacote.

### 2. Throughput teórico vs medido (GBN e SR)

Janela deslizante (mesmos `L_pay`, `RTT`, `t_trans`): `G_win = min(R·L_pay/L_wire, N·L_pay/(RTT+t_trans))`. Com `R=1 Gbit/s` o termo do enlace (≈966 Mbit/s) não limita; domina o termo da janela, que cresce ~N vezes sobre o stop-and-wait.

| Protocolo | Janela | `G_win` teórico (kbit/s) | Medido L0 (kbit/s) |
|---|---|---|---|
| GBN | 4 | 11333 | 10184 |
| GBN | 16 | 45333 | 33987 |
| SR | 4 | 11333 | 10539 |
| SR | 16 | 45333 | 41083 |

O medido fica abaixo do teórico por overhead de protocolo/SO, mas janela maior multiplica o throughput. Em L0 GBN e SR têm o mesmo teórico; divergem sob perda/reordenação.

### 3. Comparativo sob latência (saw vs GBN vs SR, L0–L3)

Throughput medido (kbit/s). j4 = janela 4, j16 = janela 16.

| Cenário | saw | GBN j4 | GBN j16 | SR j4 | SR j16 | teór. saw | teór. j4 | teór. j16 |
|---|---|---|---|---|---|---|---|---|
| L0 | 2847,3 | 10184 | 33987 | 10539 | 41083 | 2833 | 11333 | 45333 |
| L1 | 12,6 | 50,0 | 197,3 | 50,0 | 196,9 | 20,3 | 81 | 324 |
| L2 | 9,2 | 37,2 | 145,2 | 37,4 | 145,2 | 10,2 | 40,7 | 162,6 |
| L3 | 6,3 | 25,0 | 98,2 | 25,0 | 98,2 | 6,8 | 27,1 | 108,5 |

Com janela N o emissor manda até N pacotes antes de exigir ACK, mantendo o canal cheio durante o RTT. Por isso GBN e SR seguram a vazão em L1–L3 muito melhor que o saw, e janela 16 aguenta latências mais altas que janela 4.

### 4. Comparativo sob perda (GBN vs SR, P1–P4)

Throughput em kbit/s. **Janela 4:**

| Cenário | Perda (%) | GBN tput | GBN retr | SR tput | SR retr |
|---|---|---|---|---|---|
| P1 | 1 | 9384,8 | 24 | 2611,4 | 13 |
| P2 | 5 | 7296,6 | 184 | 226,7 | 54 |
| P3 | 10 | 6881,0 | 224 | 163,7 | 100 |
| P4 | 25 | 292,1 | 569 | 44,7 | 261 |

**Janela 16:**

| Cenário | Perda (%) | GBN tput | GBN retr | SR tput | SR retr |
|---|---|---|---|---|---|
| P1 | 1 | 16538,6 | 432 | 1151,4 | 39 |
| P2 | 5 | 7071,9 | 2816 | 356,2 | 114 |
| P3 | 10 | 6781,2 | 2061 | 272,2 | 171 |
| P4 | 25 | 5108,8 | 3821 | 98,6 | 299 |

Quando perde um pacote, o GBN retransmite o lote a partir do não confirmado (os seguintes foram descartados por estarem fora de ordem); o SR retransmite só o faltante, já que bufferizou os demais. Daí o GBN gerar muito mais retransmissões (P4 janela 16: GBN 3821 vs SR 299, ~13×) mas com throughput bruto maior por manter o cano cheio. Resumindo: o SR usa a rede de forma mais eficiente (retransm. perto do nº de perdas) e o GBN é mais agressivo (mais vazão bruta, mais banda desperdiçada).

### 5. Comparativo sob reordenação R0–R2 (ponto central)

Reordenação: R0=0, R1=10, R2=25 %.

Throughput em kbit/s. **Janela 4:**

| Cenário | Reord. (%) | GBN tput | GBN retr | SR tput | SR retr |
|---|---|---|---|---|---|
| R0 | 0 | 10138,0 | 0 | 10727,1 | 0 |
| R1 | 10 | 9323,1 | 103 | 10179,0 | 9 |
| R2 | 25 | 8949,7 | 232 | 10114,8 | 23 |

**Janela 16:**

| Cenário | Reord. (%) | GBN tput | GBN retr | SR tput | SR retr |
|---|---|---|---|---|---|
| R0 | 0 | 31704,9 | 0 | 39330,5 | 0 |
| R1 | 10 | 8004,3 | 1936 | 37024,4 | 6 |
| R2 | 25 | 6135,3 | 2367 | 33085,0 | 17 |

A reordenação não perde pacote, só entrega fora de ordem. No GBN o pacote fora de ordem é descartado (o receptor só aceita em ordem), gera NACK do esperado e o emissor retransmite o lote, ou seja, trata reordenação quase como perda: joga fora pacotes que já tinham chegado e a vazão cai. Ver `gbn_R2_janela16.pcapng` (descarte do fora de ordem, NACK, rajada de retransmissões). No SR o pacote fora de ordem é bufferizado na janela; quando o faltante chega o receptor entrega tudo em ordem e nunca descarta o que já recebeu. Ele manda NACK do seq faltante e o emissor reenvia só aquele, mas sob reordenação pura o faltante está só atrasado e chega logo, então o NACK pode disparar uma retransmissão espúria (o pacote chega duas vezes). Mesmo assim é uma retransmissão única e sem desperdício. Ver `sr_R2_janela16.pcapng` (bufferização, NACK pontual, retransmissão única).

O SR é quase imune à reordenação: poucas retransmissões (6–23) e throughput quase intacto (janela 16: 39330→33085). O GBN sofre muito: na janela 16 as retransmissões explodem (R1=1936, R2=2367) e o throughput despenca de 31705 para 8004/6135.

### 6. Conclusão comparativa

Pelos dados, eu escolheria assim:

- **Canal limpo, baixa latência:** os três entregam bem; o stop-and-wait basta e é o mais simples. _(confrontar L0/P0)_
- **Latência alta, pouca perda:** janela deslizante é essencial — saw colapsa com o RTT, GBN e SR seguram a vazão. Entre os dois, empatam aqui; preferir o mais simples (GBN). _(confrontar L2/L3)_
- **Perda significativa:** o **SR é mais eficiente no uso da rede** — retransmite só o faltante (P4 janela 16: 299 retransm. vs GBN 3821). O GBN ainda entrega throughput bruto maior reenviando em lote, mas ao custo de muito desperdício de banda. _(confrontar P3/P4 na seção 4)_
- **Reordenação significativa:** **SR** é a única escolha sensata — quase imune (R2 janela 16: throughput 33085 com 17 retransm.), enquanto o GBN trata reordenação como perda (throughput 6135 com 2367 retransm.). _(seção 5)_

Sobre o tamanho de janela: janela maior multiplica a vazão em rede limpa mas amplifica o desperdício do GBN sob perda/reordenação; no SR a retransmissão é pontual e não cresce com N.

### 7. O que aprendemos

Esse trabalho deixou claro na prática vários pontos que na teoria pareciam só fórmula:

- A teoria de ARQ do Kurose acertou o caso limpo (L0: 2833 teórico vs 2847 medido), mas o modelo simples de perda `G_sw·(1-p)` ficou bem otimista. Só medindo dá pra ver que cada perda paga um timeout inteiro de 100 ms parado, e é isso que despenca a vazão — o modelo idealizado esconde esse custo.
- O timeout fixo de 100 ms é o coração do stop-and-wait. Assim que a latência encosta nele (L1), as retransmissões desnecessárias explodem e a vazão cai mais de 200×. Ficou nítido por que o stop-and-wait é preso ao RTT e por que a janela deslizante existe.
- Implementar GBN e SR mostrou o trade-off de verdade: o GBN é simples mas trata reordenação quase como perda (descarta e reenvia em lote), enquanto o SR bufferiza e quase não sente reordenação, ao custo de mais complexidade no receptor. A diferença que parecia teórica apareceu direto nos números (R2 janela 16: SR 17 retransmissões vs GBN 2367).
- Tamanho de janela não é só "maior é melhor": ajuda muito em rede boa, mas amplia o desperdício do GBN quando a rede piora.
- Fazer os dois lados conversarem (e depois com outro grupo) ensinou o quanto o formato exato do cabeçalho, o CRC e o esquema de portas P/P+1 pesam na interoperabilidade — qualquer detalhe fora do combinado e a conexão não fecha.

No fim, deu pra entender por que protocolos reais como o TCP usam janela deslizante com timeout adaptativo no lugar de um valor fixo, e por que a forma de retransmitir (em lote ou seletiva) muda tudo dependendo da rede.
