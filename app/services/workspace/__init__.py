# -*- coding: utf-8 -*-
"""
Workspace Services — Engenharia Reversa Protheus
Origem: ExtraiRPO (Joni) adaptado para BiizHubOps Supreme.

Modulos:
- parser_sx: Parse de CSVs SX (SX2, SX3, SIX, SX7, SX1, SX5, SX6, SX9, SXA, SXB)
- parser_source: Parse de codigo-fonte ADVPL/TLPP
- ingestor: Pipeline de ingestao (CSV/DB -> SQLite)
- knowledge: Queries de contexto para agente IA
- build_vinculos: Grafo de relacionamentos (11 tipos)
- vectorstore: Adapter para ChromaDB ou FTS5+embeddings
"""
