"""
Schema de referencia das tabelas de metadados do TOTVS Protheus.

Autocontido — carregado ao importar o modulo, sem dependencia de banco.
Usado pelo ingestor, equalizador e prompt extrator para:
  - Validar colunas antes de gerar INSERT (rejeitar colunas inexistentes)
  - Gerar arquivos de exemplo com colunas corretas
  - Servir de referencia para o agente IA

Fonte: INFORMATION_SCHEMA do SQL Server (Protheus 12.1.2310+)
Atualizado: 2026-03-25
"""

# Formato: {COLUNA: tipo_sql}
# Colunas de controle (D_E_L_E_T_, R_E_C_N_O_, R_E_C_D_E_L_) incluidas
# para referencia mas tratadas separadamente pelo equalizador/ingestor.

SX2_COLUMNS = {
    "X2_CHAVE": "varchar(3)",
    "X2_PATH": "varchar(40)",
    "X2_ARQUIVO": "varchar(8)",
    "X2_NOME": "varchar(30)",
    "X2_NOMESPA": "varchar(30)",
    "X2_NOMEENG": "varchar(30)",
    "X2_ROTINA": "varchar(40)",
    "X2_MODO": "varchar(1)",
    "X2_MODOUN": "varchar(1)",
    "X2_MODOEMP": "varchar(1)",
    "X2_DELET": "float",
    "X2_TTS": "varchar(1)",
    "X2_UNICO": "varchar(250)",
    "X2_PYME": "varchar(1)",
    "X2_MODULO": "float",
    "X2_DISPLAY": "varchar(254)",
    "X2_SYSOBJ": "varchar(100)",
    "X2_USROBJ": "varchar(100)",
    "X2_POSLGT": "varchar(1)",
    "X2_CLOB": "varchar(1)",
    "X2_AUTREC": "varchar(1)",
    "X2_TAMFIL": "float",
    "X2_TAMUN": "float",
    "X2_TAMEMP": "float",
    "X2_STAMP": "varchar(1)",
    "X2_INSDT": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SX3_COLUMNS = {
    "X3_ARQUIVO": "varchar(3)",
    "X3_ORDEM": "varchar(2)",
    "X3_CAMPO": "varchar(10)",
    "X3_TIPO": "varchar(1)",
    "X3_TAMANHO": "float",
    "X3_DECIMAL": "float",
    "X3_TITULO": "varchar(12)",
    "X3_TITSPA": "varchar(12)",
    "X3_TITENG": "varchar(12)",
    "X3_DESCRIC": "varchar(25)",
    "X3_DESCSPA": "varchar(25)",
    "X3_DESCENG": "varchar(25)",
    "X3_PICTURE": "varchar(45)",
    "X3_VALID": "varchar(160)",
    "X3_USADO": "varchar(120)",
    "X3_RELACAO": "varchar(160)",
    "X3_F3": "varchar(6)",
    "X3_NIVEL": "float",
    "X3_RESERV": "varchar(16)",
    "X3_CHECK": "varchar(1)",
    "X3_TRIGGER": "varchar(1)",
    "X3_PROPRI": "varchar(1)",
    "X3_BROWSE": "varchar(1)",
    "X3_VISUAL": "varchar(1)",
    "X3_CONTEXT": "varchar(1)",
    "X3_OBRIGAT": "varchar(8)",
    "X3_VLDUSER": "varchar(160)",
    "X3_CBOX": "varchar(128)",
    "X3_CBOXSPA": "varchar(128)",
    "X3_CBOXENG": "varchar(128)",
    "X3_PICTVAR": "varchar(50)",
    "X3_WHEN": "varchar(100)",
    "X3_INIBRW": "varchar(100)",
    "X3_GRPSXG": "varchar(3)",
    "X3_FOLDER": "varchar(1)",
    "X3_PYME": "varchar(1)",
    "X3_CONDSQL": "varchar(250)",
    "X3_CHKSQL": "varchar(250)",
    "X3_IDXSRV": "varchar(1)",
    "X3_ORTOGRA": "varchar(1)",
    "X3_IDXFLD": "varchar(1)",
    "X3_TELA": "varchar(15)",
    "X3_PICBRV": "varchar(50)",
    "X3_AGRUP": "varchar(3)",
    "X3_POSLGT": "varchar(1)",
    "X3_MODAL": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SIX_COLUMNS = {
    "INDICE": "varchar(3)",
    "ORDEM": "varchar(1)",
    "CHAVE": "varchar(160)",
    "DESCRICAO": "varchar(70)",
    "DESCSPA": "varchar(70)",
    "DESCENG": "varchar(70)",
    "PROPRI": "varchar(1)",
    "F3": "varchar(160)",
    "NICKNAME": "varchar(10)",
    "SHOWPESQ": "varchar(1)",
    "IX_VIRTUAL": "varchar(1)",
    "IX_VIRCUST": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SX1_COLUMNS = {
    "X1_GRUPO": "varchar(10)",
    "X1_ORDEM": "varchar(2)",
    "X1_PERGUNT": "varchar(30)",
    "X1_PERSPA": "varchar(30)",
    "X1_PERENG": "varchar(30)",
    "X1_VARIAVL": "varchar(6)",
    "X1_TIPO": "varchar(1)",
    "X1_TAMANHO": "float",
    "X1_DECIMAL": "float",
    "X1_PRESEL": "float",
    "X1_GSC": "varchar(1)",
    "X1_VALID": "varchar(160)",
    "X1_VAR01": "varchar(15)",
    "X1_DEF01": "varchar(15)",
    "X1_DEFSPA1": "varchar(15)",
    "X1_DEFENG1": "varchar(15)",
    "X1_CNT01": "varchar(60)",
    "X1_VAR02": "varchar(15)",
    "X1_DEF02": "varchar(15)",
    "X1_DEFSPA2": "varchar(15)",
    "X1_DEFENG2": "varchar(15)",
    "X1_CNT02": "varchar(60)",
    "X1_VAR03": "varchar(15)",
    "X1_DEF03": "varchar(15)",
    "X1_DEFSPA3": "varchar(15)",
    "X1_DEFENG3": "varchar(15)",
    "X1_CNT03": "varchar(60)",
    "X1_VAR04": "varchar(15)",
    "X1_DEF04": "varchar(15)",
    "X1_DEFSPA4": "varchar(15)",
    "X1_DEFENG4": "varchar(15)",
    "X1_CNT04": "varchar(60)",
    "X1_VAR05": "varchar(15)",
    "X1_DEF05": "varchar(15)",
    "X1_DEFSPA5": "varchar(15)",
    "X1_DEFENG5": "varchar(10)",
    "X1_CNT05": "varchar(60)",
    "X1_F3": "varchar(6)",
    "X1_PYME": "varchar(1)",
    "X1_GRPSXG": "varchar(3)",
    "X1_HELP": "varchar(14)",
    "X1_PICTURE": "varchar(40)",
    "X1_IDFIL": "varchar(6)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SX5_COLUMNS = {
    "X5_FILIAL": "varchar(2)",
    "X5_TABELA": "varchar(2)",
    "X5_CHAVE": "varchar(6)",
    "X5_DESCRI": "varchar(55)",
    "X5_DESCSPA": "varchar(55)",
    "X5_DESCENG": "varchar(55)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SX6_COLUMNS = {
    "X6_FIL": "varchar(2)",
    "X6_VAR": "varchar(10)",
    "X6_TIPO": "varchar(1)",
    "X6_DESCRIC": "varchar(50)",
    "X6_DSCSPA": "varchar(50)",
    "X6_DSCENG": "varchar(50)",
    "X6_DESC1": "varchar(50)",
    "X6_DSCSPA1": "varchar(50)",
    "X6_DSCENG1": "varchar(50)",
    "X6_DESC2": "varchar(50)",
    "X6_DSCSPA2": "varchar(50)",
    "X6_DSCENG2": "varchar(50)",
    "X6_CONTEUD": "varchar(250)",
    "X6_CONTSPA": "varchar(250)",
    "X6_CONTENG": "varchar(250)",
    "X6_PROPRI": "varchar(1)",
    "X6_PYME": "varchar(1)",
    "X6_VALID": "varchar(160)",
    "X6_INIT": "varchar(128)",
    "X6_DEFPOR": "varchar(250)",
    "X6_DEFSPA": "varchar(250)",
    "X6_DEFENG": "varchar(250)",
    "X6_EXPDEST": "varchar(1)",
    "X6_ACTIVE": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SX7_COLUMNS = {
    "X7_CAMPO": "varchar(10)",
    "X7_SEQUENC": "varchar(3)",
    "X7_REGRA": "varchar(200)",
    "X7_CDOMIN": "varchar(10)",
    "X7_TIPO": "varchar(1)",
    "X7_SEEK": "varchar(1)",
    "X7_ALIAS": "varchar(3)",
    "X7_ORDEM": "float",
    "X7_CHAVE": "varchar(200)",
    "X7_CONDIC": "varchar(40)",
    "X7_PROPRI": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SX9_COLUMNS = {
    "X9_DOM": "varchar(3)",
    "X9_IDENT": "varchar(3)",
    "X9_CDOM": "varchar(3)",
    "X9_EXPDOM": "varchar(250)",
    "X9_EXPCDOM": "varchar(250)",
    "X9_PROPRI": "varchar(1)",
    "X9_LIGDOM": "varchar(1)",
    "X9_LIGCDOM": "varchar(1)",
    "X9_CONDSQL": "varchar(250)",
    "X9_USEFIL": "varchar(1)",
    "X9_ENABLE": "varchar(1)",
    "X9_VINFIL": "varchar(1)",
    "X9_CHVFOR": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SXA_COLUMNS = {
    "XA_ALIAS": "varchar(3)",
    "XA_ORDEM": "varchar(1)",
    "XA_DESCRIC": "varchar(30)",
    "XA_DESCSPA": "varchar(30)",
    "XA_DESCENG": "varchar(30)",
    "XA_PROPRI": "varchar(1)",
    "XA_AGRUP": "varchar(3)",
    "XA_TIPO": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

SXB_COLUMNS = {
    "XB_ALIAS": "varchar(6)",
    "XB_TIPO": "varchar(1)",
    "XB_SEQ": "varchar(2)",
    "XB_COLUNA": "varchar(2)",
    "XB_DESCRI": "varchar(20)",
    "XB_DESCSPA": "varchar(20)",
    "XB_DESCENG": "varchar(20)",
    "XB_CONTEM": "varchar(250)",
    "XB_WCONTEM": "varchar(250)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

XXA_COLUMNS = {
    "XXA_DOM": "varchar(10)",
    "XXA_CDOM": "varchar(10)",
    "XXA_SEQUEN": "varchar(3)",
    "XXA_DESCRI": "varchar(60)",
    "XXA_DSCSPA": "varchar(60)",
    "XXA_DSCENG": "varchar(60)",
    "XXA_TYPE": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

XAM_COLUMNS = {
    "XAM_FILIAL": "varchar(2)",
    "XAM_CLASSI": "varchar(1)",
    "XAM_ANONIM": "varchar(1)",
    "XAM_JUSTIF": "varchar(200)",
    "XAM_FIELD": "varchar(10)",
    "XAM_MODULE": "varchar(2)",
    "XAM_IDXAL": "varchar(3)",
    "XAM_ALIAS": "varchar(3)",
    "XAM_IDENT": "varchar(1)",
    "XAM_PROPRI": "varchar(1)",
    "XAM_JUSTI2": "varchar(200)",
    "XAM_SINUSE": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

XAL_COLUMNS = {
    "XAL_FILIAL": "varchar(2)",
    "XAL_ID": "varchar(3)",
    "XAL_DESC": "varchar(50)",
    "XAL_TIPO": "varchar(1)",
    "XAL_PROPRI": "varchar(1)",
    "D_E_L_E_T_": "varchar(1)",
    "R_E_C_N_O_": "bigint",
    "R_E_C_D_E_L_": "bigint",
}

# =========================================================
# INDICE CENTRALIZADO
# =========================================================

# Mapa tabela -> colunas validas (sem colunas de controle)
METADATA_SCHEMA = {
    "SX2": SX2_COLUMNS,
    "SX3": SX3_COLUMNS,
    "SIX": SIX_COLUMNS,
    "SX1": SX1_COLUMNS,
    "SX5": SX5_COLUMNS,
    "SX6": SX6_COLUMNS,
    "SX7": SX7_COLUMNS,
    "SX9": SX9_COLUMNS,
    "SXA": SXA_COLUMNS,
    "SXB": SXB_COLUMNS,
    "XXA": XXA_COLUMNS,
    "XAM": XAM_COLUMNS,
    "XAL": XAL_COLUMNS,
}

# Colunas de controle — tratamento especial em todos os contextos
CONTROL_COLUMNS = {"R_E_C_N_O_", "R_E_C_D_E_L_", "S_T_A_M_P_", "I_N_S_D_T_"}


def get_valid_columns(table_prefix):
    """Retorna set de colunas validas para uma tabela de metadado.

    Exclui colunas de controle (R_E_C_N_O_, R_E_C_D_E_L_).
    Mantem D_E_L_E_T_ (tratado separadamente).
    """
    schema = METADATA_SCHEMA.get(table_prefix.upper(), {})
    return {col for col in schema if col not in CONTROL_COLUMNS}


def filter_valid_columns(table_prefix, row_dict):
    """Filtra um dict removendo colunas que nao existem na tabela.

    Retorna (filtered_dict, removed_columns).
    """
    valid = get_valid_columns(table_prefix)
    if not valid:
        # Tabela desconhecida — sem filtro (passthrough)
        return dict(row_dict), []

    filtered = {}
    removed = []
    for k, v in row_dict.items():
        key_upper = k.strip().upper() if isinstance(k, str) else str(k).upper()
        if key_upper in CONTROL_COLUMNS:
            continue  # Sempre remove controle
        if key_upper in valid:
            filtered[key_upper] = v
        else:
            removed.append(key_upper)

    return filtered, removed
