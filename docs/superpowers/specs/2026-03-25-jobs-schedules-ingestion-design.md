# Jobs & Schedules Ingestion — Design Spec

## Goal
Ingest Job (AppServer INI) and Schedule (Protheus agenda) CSVs into the existing SQLite database, create automatic vinculos linking rotinas to fontes via function name lookup, and expose the data in the Explorer tree view.

## Data Sources

### job_detalhado_bash.csv (215 rows)
- Delimiter: `;`
- Columns: `Arquivo`, `Sessao`, `Rotina_Main`, `RefreshRate`, `Parametros`
- Each row = one job session configured in an AppServer INI
- Multiple sessions can share the same INI file

### schedule_decodificado.csv (97 rows)
- Delimiter: `;`
- Columns: `Codigo`, `Rotina`, `Empresa_Filial`, `Environment`, `Modulo`, `Status`, `Tipo_Recorrencia`, `Detalhe_Recorrencia`, `Execucoes_Dia`, `Intervalo_HH_MM`, `Data_Fim_Recorrencia`, `Hora_Inicio`, `Data_Criacao`, `Ultima_Execucao`, `Ultima_Hora`, `Recorrencia_Raw`
- PK is (Codigo, Empresa_Filial) since same schedule can run on multiple filiais

## Architecture

### New Tables

**`jobs`** — PK: `(arquivo_ini, sessao)`

| Column | Type | Source Column |
|--------|------|---------------|
| arquivo_ini | TEXT | Arquivo |
| sessao | TEXT | Sessao |
| rotina | TEXT | Rotina_Main |
| refresh_rate | INTEGER NULL | RefreshRate (NULL if "N/A") |
| parametros | TEXT | Parametros |

**`schedules`** — PK: `(codigo, empresa_filial)`

| Column | Type | Source Column |
|--------|------|---------------|
| codigo | TEXT | Codigo |
| rotina | TEXT | Rotina (cleaned) |
| empresa_filial | TEXT | Empresa_Filial |
| environment | TEXT | Environment |
| modulo | INTEGER | Modulo |
| status | TEXT | Status |
| tipo_recorrencia | TEXT | Tipo_Recorrencia |
| detalhe_recorrencia | TEXT | Detalhe_Recorrencia |
| execucoes_dia | INTEGER NULL | Execucoes_Dia |
| intervalo | TEXT | Intervalo_HH_MM |
| hora_inicio | TEXT | Hora_Inicio |
| data_criacao | TEXT | Data_Criacao |
| ultima_execucao | TEXT | Ultima_Execucao |
| ultima_hora | TEXT | Ultima_Hora |
| recorrencia_raw | TEXT | Recorrencia_Raw |

### Function Name Extraction

Schedule rotinas often include parameters: `U_MGFWSC28('','01','010041')` or `U_MGFFINCB()`.
Job rotinas are clean: `U_MGFFATF4`.

Extraction regex: `^(U_\w+|[A-Z]\w+)` — strip parentheses and arguments to get the function name.

### Vinculos (in build_vinculos.py)

Two new vinculo types:

1. **`job_executa_funcao`**: `origem_tipo=job, origem=sessao, destino_tipo=funcao, destino=function_name`
2. **`schedule_executa_funcao`**: `origem_tipo=schedule, origem=codigo, destino_tipo=funcao, destino=function_name`

The existing `funcao_definida_em` vinculos already link funcao→fonte, so the chain is:
```
job/schedule → funcao → fonte (arquivo.prw)
```

### Explorer Integration

Add two top-level nodes in the `/explorer/modules` response (after Webservices):

- **Jobs** — grouped by arquivo_ini, showing sessions with rotina + refresh_rate
- **Schedules** — grouped by status (Ativo/Inativo), showing rotina + frequencia + filiais

New endpoints:
- `GET /explorer/jobs` — returns job tree nodes
- `GET /explorer/schedules` — returns schedule tree nodes

### Pipeline Integration

Jobs and Schedules are parsed in **Phase 1** (`run_fase1`), alongside the SX files. The CSV filenames to detect:
- `job_detalhado_bash.csv` (or `job_detalhado*.csv`)
- `schedule_decodificado.csv` (or `schedule_decodificado*.csv`)
