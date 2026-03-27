---
name: protheus_structure
description: Estrutura completa do Protheus - modulos, tabelas por prefixo, dicionario SX
intents: [table_info, module_info, structure_info]
keywords: [tabela, table, modulo, module, SA1, SA2, SB1, SC5, SD1, SE1, SF1, prefixo, alias, estrutura, cadastro, financeiro, compras, faturamento, estoque]
priority: 80
max_tokens: 800
specialist: "database"
---

## ESTRUTURA DO PROTHEUS

### Modulos Principais

| Sigla | Nome | Area |
|-------|------|------|
| SIGAFIN | Financeiro | Contas a pagar/receber, fluxo de caixa, conciliacao bancaria |
| SIGAFAT | Faturamento | Ciclo de vendas, NF-e/NFC-e, calculo fiscal automatico |
| SIGACOM | Compras | Cotacoes, pedidos, aprovacao, gestao de fornecedores |
| SIGAEST | Estoque/Custos | Controle FIFO/LIFO/medio, saldos, inventario |
| SIGAFIS | Livros Fiscais | Impostos federais/estaduais/municipais, SPED |
| SIGACTB | Contabilidade | Plano de contas, lancamentos, consolidacao |
| SIGAPCP | Planejamento Producao | MRP, ordens de producao, apontamento |
| SIGAMNT | Manutencao de Ativos | Planos preventivos, OS, historico de bens |
| SIGALOJA | PDV/Varejo | Frente de caixa, cupom fiscal |
| SIGAGPE | RH/Folha | Admissao, folha, beneficios, ferias |
| SIGATMK | Call Center/SAC | Atendimento, televendas, scripts |
| SIGACRM | CRM | Gestao de clientes, oportunidades |
| SIGAWMS | WMS | Armazem, logistica interna |
| SIGATMS | TMS | Transporte, frete, rotas |
| SIGAATF | Ativo Fixo | Imobilizado, depreciacao |
| SIGAGCT | Contratos | Ciclo de vida, obrigacoes |
| SIGAPMS | Projetos | Planejamento, execucao |
| SIGACFG | Configurador | Dicionario de dados, menus, parametros |
| SIGATAF | Automacao Fiscal | Compliance fiscal automatizado |
| SIGAPCO | Orcamento | Planejamento orcamentario |
| SIGAOMS | Distribuicao | Pedido-a-entrega |
| SIGAEIC | Comercio Exterior | Import/export |

### Tabelas por Prefixo

#### SA — Cadastros
| Alias | Descricao |
|-------|-----------|
| SA1 | Clientes |
| SA2 | Fornecedores |
| SA3 | Vendedores |
| SA4 | Transportadoras |
| SA5 | Amarracao Produto x Fornecedor |
| SA6 | Bancos |
| SA7 | Amarracao Produto x Cliente |
| SA9 | Tecnicos |
| SAH | Unidades de Medida |
| SAI | Solicitantes |
| SAJ | Grupos de Compras |
| SAK | Aprovadores |
| SAL | Grupos de Aprovacao |
| SAM | Codigos EDI |
| SAP | Conversao de Unidades |

#### SB — Produtos / Estoque
| Alias | Descricao |
|-------|-----------|
| SB1 | Descricao Generica do Produto |
| SB2 | Saldos Fisico e Financeiro |
| SB3 | Demandas |
| SB5 | Dados Adicionais do Produto |
| SB6 | Saldo em Poder de Terceiros |
| SB7 | Lancamentos do Inventario |
| SB8 | Saldos por Lote |
| SBE | Enderecos (WMS) |
| SBF | Saldos por Endereco |
| SBM | Grupo de Produto |

#### SC — Compras / Vendas / Producao
| Alias | Descricao |
|-------|-----------|
| SC1 | Solicitacoes de Compra |
| SC2 | Ordens de Producao |
| SC5 | Pedidos de Venda (cabecalho) |
| SC6 | Itens dos Pedidos de Venda |
| SC7 | Pedidos de Compra |
| SC8 | Cotacoes |
| SC9 | Pedidos Liberados |
| SCJ | Orcamentos |
| SCK | Itens de Orcamento |

#### SD — Movimentacoes de Estoque
| Alias | Descricao |
|-------|-----------|
| SD1 | Itens NF de Entrada |
| SD2 | Itens NF de Saida |
| SD3 | Movimentacoes Internas |
| SD4 | Requisicoes Empenadas |
| SDE | Rateios da NF |

#### SE — Financeiro
| Alias | Descricao |
|-------|-----------|
| SE1 | Titulos a Receber |
| SE2 | Titulos a Pagar |
| SE5 | Movimentacao Bancaria |
| SEU | Multiplas Naturezas por Titulo |

#### SF — Fiscal / Notas Fiscais
| Alias | Descricao |
|-------|-----------|
| SF1 | Cabecalho NF Entrada |
| SF2 | Cabecalho NF Saida |
| SF3 | Livros Fiscais |
| SF4 | Tipos de Entrada e Saida (TES) |
| SF5 | Tipos de Movimentacao |
| SF6 | Guias de Recolhimento |
| SF9 | CIAP |
| SFB | Impostos Variaveis |
| SFC | Amarracao TES x Impostos |

#### SG — Estruturas de Montagem
| Alias | Descricao |
|-------|-----------|
| SG1 | Estrutura dos Produtos (BOM) |
| SG2 | Operacoes |
| SG6 | Grupo de Recursos |

#### SH — Carga de Maquina
| Alias | Descricao |
|-------|-----------|
| SH1 | Recursos |
| SH6 | Movimentacao da Producao |
| SH7 | Calendario |

#### SI — Contabilidade
| Alias | Descricao |
|-------|-----------|
| SI1 | Plano de Contas |
| SI2 | Lancamentos Contabeis |
| SI3 | Centros de Custos |
| SIX | Indices (dicionario) |

#### SN — Ativo Fixo
| Alias | Descricao |
|-------|-----------|
| SN1 | Cadastro de Ativo Imobilizado |
| SN3 | Saldos e Valores |
| SN4 | Movimentacoes do Ativo |

#### SR — Folha de Pagamento
| Alias | Descricao |
|-------|-----------|
| SRA | Funcionarios |
| SRB | Dependentes |
| SRC | Movimento Mensal |
| SRJ | Funcoes |
| SRV | Verbas |

#### ST — Manutencao
| Alias | Descricao |
|-------|-----------|
| ST4 | Servicos de Manutencao |
| ST9 | Bem |
| STJ | Ordens de Servico |
| STS | Historico de Manutencao |

### Dicionario de Dados (Tabelas SX)

| Tabela | Nome | Finalidade |
|--------|------|------------|
| SX1 | Perguntas | Parametrizacao de relatorios e movimentacoes |
| SX2 | Tabelas de Dados | Registro de todas as tabelas disponiveis (alias, path) |
| SX3 | Campos das Tabelas | Estrutura de campos (tipo, tamanho, validacao, picture) |
| SX4 | Agenda | Schedule de processos |
| SX5 | Tabelas Genericas | Cadastros codigo/valor simples |
| SX6 | Parametros do Sistema | Configuracoes gerais (GetMV) |
| SX7 | Gatilhos de Campos | Preenchimento automatico entre campos |
| SX8 | Sequencia de Documentacao | Numeracao sequencial |
| SX9 | Relacionamento entre Arquivos | Joins entre tabelas |
| SXA | Pastas Cadastrais | Abas nos formularios |
| SXB | Consulta Padrao | Telas de pesquisa F3 |
| SXE | Sequencia de Numeracao (+1) | Auto-incremento |
| SXG | Tamanho Padrao para Campos | Definicoes de tamanho por grupo |
| SXK | Perguntas por Usuario | SX1 customizado por usuario |
| SXO/SXP | Log por Tabela | Controle de auditoria |
| SIX | Indices | Indices das tabelas (chaves de busca) |
