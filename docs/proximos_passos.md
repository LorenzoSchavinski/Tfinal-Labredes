---

# Próximos passos para concluir a entrega

Tudo que depende de código/artefatos está pronto e verificado. O que falta é trabalho manual de laboratório (capturas em duas máquinas, números medidos, PDF) e a preparação da apresentação. Esta é a sequência completa.

Prazos: entrega 29/06 no Moodle. Apresentação 29/06 e 06/07.

## 1. Preparação do ambiente

- [ ] Duas máquinas distintas na mesma rede local. Anotar o IP da máquina que roda o receiver.
- [ ] Escolher uma porta P (ex.: 6000). O receiver escuta em P; o sender escuta ACKs em P+1.
- [ ] Instalar Wireshark nas duas máquinas e o clumsy na máquina que vai aplicar a perturbação (sender ou receiver).
- [ ] Criar o arquivo de teste com pelo menos 50 pacotes de dados. Com payload de 255 bytes, são necessários ~13 KB; usar ~64 KB (~251 pacotes) por margem:
  - Windows PowerShell: `[IO.File]::WriteAllBytes("teste.bin", (0..63999 | ForEach-Object { $_ % 256 }))`
  - Linux/macOS: `head -c 64000 /dev/urandom > teste.bin`
- [ ] Confirmar que os testes ainda passam antes de começar: `python -m pytest -q` deve dar `29 passed`.

## 2. Capturas obrigatórias (58 arquivos .pcapng)

Seguir o passo a passo detalhado em [docs/runbook_capturas.md](runbook_capturas.md): comandos exatos por cenário, configuração do clumsy por nível e a lista completa para marcar.

Matriz resumida:

| Modo | Cenários | Janelas | Qtd |
|------|----------|---------|-----|
| saw  | L0-L3, P0-P4 | (n/a) | 9 |
| gbn  | L0-L3, P0-P4, R0-R2 | 4 e 16 | 24 |
| sr   | L0-L3, P0-P4, R0-R2 | 4 e 16 | 24 |
| crc  | demonstração CRC32 | (n/a) | 1 |
| **Total** | | | **58** |

- [ ] Para cada cenário: iniciar a captura no Wireshark, rodar receiver e sender, parar a captura, salvar como `.pcapng` com o nome EXATO do cenário (ex.: `saw_L2.pcapng`, `gbn_P3_janela4.pcapng`, `sr_R2_janela16.pcapng`). Nome errado perde ponto.
- [ ] Anotar, a cada execução, o throughput e o número de retransmissões que o sender imprime (`[sender] throughput: ... kbit/s` e `[sender] retransmissões: N`). Esses são os números medidos do relatório.
- [ ] Guardar todos os `.pcapng` em uma pasta `capturas/`.

### Demonstração do CRC32 (saw_crc.pcapng)

O clumsy não corrompe payload, então usar o relay `corrupt.py`. As portas precisam satisfazer: porta do receiver = porta de escuta do relay menos 1 (para o ACK do receiver, em P+1, chegar no relay). Três terminais:

```
# receiver (porta 6000; ACKs vão para 6001)
python srtp.py --listen --port 6000 --mode saw --out recebido.bin

# relay que corrompe 1 pacote (escuta em 6001 = P+1 do receiver, repassa para 6000)
python corrupt.py --listen-port 6001 --target-host 127.0.0.1 --target-port 6000 --which 1

# sender aponta para o relay
python srtp.py --host 127.0.0.1 --port 6001 --mode saw --file teste.bin
```

- [ ] Capturar mostrando o pacote corrompido sendo descartado (sem NACK) e a retransmissão por timeout. Salvar como `saw_crc.pcapng`.

## 3. Números medidos e teóricos

- [ ] Medidos: usar os valores que o sender imprime em cada execução real (throughput e retransmissões), por cenário.
- [ ] Teóricos: o relatório já traz as fórmulas (Kurose 3.4). Para conferir/gerar os valores teóricos localmente, rodar o `bench.py` ajustando para a rede real:
  - `--rate` = taxa do enlace em bits/s (ex.: `1e9` para Gigabit, `1e8` para 100 Mbit).
  - `--base-rtt` = RTT base medido (ping entre as máquinas), em segundos (ex.: 0.5 ms -> `5e-4`).
  - Exemplo: `python bench.py --mode saw --rate 1e9 --base-rtt 5e-4`
- [ ] Declarar no relatório as premissas usadas (taxa do enlace e RTT base), pois o teórico depende delas.

## 4. Relatório (docs/relatorio.md -> PDF)

A estrutura, as fórmulas e as explicações já estão escritas. Falta preencher os dados e exportar.

- [ ] Preencher `**Integrantes:**` e `**Data:**` no topo.
- [ ] Preencher todas as células marcadas `<medir>` e `<calcular>` com os números reais (throughput, retransmissões, teórico vs medido), em todas as tabelas das Partes 1 e 2.
- [ ] Conferir que as análises (transições de latência em torno do timeout de 100 ms, efeito da perda, GBN vs SR sob reordenação, impacto do tamanho de janela, conclusão) batem com os números medidos.
- [ ] Exportar para PDF: `docs/relatorio.pdf`. Opções: pandoc (`pandoc docs/relatorio.md -o docs/relatorio.pdf`), extensão Markdown PDF do VS Code, ou imprimir para PDF.
- [ ] **Verificar que o PDF tem no máximo 5 páginas.** Se passar, comprimir o texto/tabelas.

## 5. Empacotamento da entrega (.zip)

- [ ] Usar o comando de empacotamento documentado no [README.md](../README.md) (ele monta uma cópia limpa só com os entregáveis).
- [ ] O zip deve conter: fontes `.py` (`srtp.py`, `packet.py`, `sender.py`, `receiver.py`, `corrupt.py`, `bench.py`, `test_*.py`), `README.md`, `docs/relatorio.pdf`, e a pasta `capturas/` com os 58 `.pcapng`.
- [ ] O zip NÃO pode conter: `__pycache__/`, `.pytest_cache/`, arquivos `*.bin`, `T2_20261.pdf`, os rascunhos markdown (`docs/relatorio.md`, `docs/runbook_capturas.md`, este arquivo) nem `docs/superpowers/`.
- [ ] Nomear o zip com os nomes dos integrantes. Apenas um integrante envia pelo Moodle até o prazo.

## 6. Preparação da apresentação

- [ ] **Todos os integrantes precisam entender o código** (código de LLM sem compreensão demonstrada = nota zero). Estudar: o cabeçalho de 9 bytes (`packet.py`), o handshake de 3 vias e o encerramento de 2 vias (`sender.py`/`receiver.py`), os três modos (saw/gbn/sr), o timeout fixo de 100 ms, o CRC32, e o modelo de portas P / P+1.
- [ ] **Combinar com o outro grupo antes do teste de interoperabilidade**, confirmando os dois pontos de contrato que o enunciado deixa em aberto (ambos documentados no README):
  - Convenção de NACK: flag NACK = 1, flag ACK = 0, e o campo ACK carrega o número de sequência do pacote faltante/esperado.
  - Layout do cabeçalho de 9 bytes (big-endian, posições de bit exatas) e CRC32 sobre cabeçalho (campo CRC zerado) + payload.
  - Portas: nosso receiver envia ACKs para (IP_do_sender, P+1) e nosso sender escuta ACKs em P+1, conforme o enunciado.
- [ ] **Teste de interoperabilidade ao vivo**: nosso sender com o receiver do outro grupo e vice-versa; transferir um arquivo; sucesso = arquivo idêntico ao original (hash).

## 7. Checklist final antes de enviar

- [ ] 58 `.pcapng` presentes e com os nomes exatos, em `capturas/`.
- [ ] `docs/relatorio.pdf` com no máximo 5 páginas, todas as células preenchidas, integrantes e data preenchidos.
- [ ] `.zip` sem binários/temporários/arquivos internos.
- [ ] `python -m pytest -q` -> `29 passed`.
- [ ] Instruções de execução do README conferem com a CLI real.

---
