---
name: tdn_advpl_functions
description: Referencia rapida das funcoes AdvPL/TLPP mais usadas no Protheus, agrupadas por categoria
intents: [knowledge_search, procedure_lookup, table_info, general]
keywords: [advpl, funcao, function, tlpp, string, array, data, date, arquivo, file, http, rest, xml, json, ini, rpo, banco, database, sql, impressao, print, conversion, tipo, type, variavel, global, memoria, hash, crypt, email]
priority: 70
max_tokens: 1500
specialist: "knowledge"
---

## Funcoes AdvPL/TLPP — Referencia Rapida por Categoria

Fonte: TDN TOTVS (tdn.totvs.com/display/tec/AdvPL)

### Manipulacao de String (51 funcoes)
AllTrim, At, ATail, Chr, Asc, Descend, Empty, HardCR, IsAlpha, IsDigit, IsLower, IsUpper, Left, Len, Lower, LTrim, MemoLine, MemoRead, MemoWrite, MLCount, Pad, PadC, PadL, PadR, Replicate, Right, RTrim, Space, Str, StrTran, StrZero, Stuff, SubStr, Transform, Trim, Type, Upper, Val, ValType, CharMirr, RAt, StrIConv, StrOConv, Soundex, CharOnly, CharRem, CharRepl, CharSub, TokenSep, TokenNum

### Manipulacao de Arquivo e IO (52 funcoes)
FCreate, FOpen, FClose, FRead, FWrite, FSeek, FErase, FRename, File, Directory, MakeDir, DirChange, DirRemove, CurDir, FError, FLock, FUnLock, CpT2S, CpS2T, TFileOpen, TFileClose, TFileRead, TFileWrite, CopyFile, MoveFile, FileExists, DiskSpace, IsDirectory, PathName, FileName, FileExt

### Manipulacao de Data (17 funcoes)
CtoD, DtoC, DtoS, StoD, Date, Day, Month, Year, DoW, Time, Seconds, ElapTime, DaysInMonth, IsLeapYear, TimeToSec, SecToTime, DateDiffDay

### Conversao entre Tipos (24 funcoes)
CtoD, DtoC, DtoS, StoD, Str, Val, Transform, CValToChar, HexStrDump, NtoBit, BitToN, AscToHex, HexToAsc, BinToHex, HexToBin, CToN, NToC

### Interface HTTP / REST (33 funcoes)
HttpGet, HttpPost, HttpPut, HttpDelete, HttpPatch, HttpSetHeader, HttpGetStatus, HttpSetTimeOut, HttpSetProxy, HttpSetCertificate, HttpSetSSL, HTTPQuoteURL, WsMethodDef, WsSend, WsReceive, FWRest, FWSoapClient

### Manipulacao de Array (12 funcoes)
AAdd, ADel, AIns, ASize, ASort, AScan, AEval, ACopy, AClone, AFill, ATail, Array

### HashMap (11 + 25 funcoes)
HMNew, HMSet, HMGet, HMDel, HMGetKey, HMGetVal, HMCount, HMClone, HMClear, HMKeys, HMVals
Variaveis globais HashMap: PutGlbValue, GetGlbValue, ClearGlbValue, GlbLock, GlbUnlock

### Tratamento de XML (13 funcoes)
XmlParser, XmlParserFile, XmlSaveFile, XmlChildEx, XmlGetAttr, XmlSetAttr, XmlAddChild, XmlDelChild, XmlCData, XmlToString

### Configuracao INI (11 funcoes)
GetPvProfString, WriteProfString, GetProfileString, GetPvProf, SetPvProf, AProfString

### RPO (9 funcoes)
GetSrcComments, IsInCallStack, ProcName, ProcLine, RpcSetEnv, RpcClearEnv, GetRpoInfo, SetKeyBlock

### Controle de Processamento (18 funcoes)
Processa, ProcRegua, IncProc, SetRegua, MsAguarde, MsgRun, MsgStop, MsgYesNo, MsgInfo, MsgAlert, Aviso, FWAlertSuccess, FWAlertError

### Banco de Dados / DBAccess (funcoes-chave)
TCQuery, TCSqlExec, DbSelectArea, DbSetOrder, DbSeek, DbSkip, DbGoTop, DbGoBottom, MsSeek, Reclock, MsUnlock, TCSetField, TCSPExec, FWExecView, MsExecAuto, FWMVCModel

### Funcoes de Framework (classes mais usadas)
FWBrowse, FWFormView, FWFormModel, FWAdapter, FWMVCModel, FWMarkBrowse, FWTemporaryTable, FWDBAccess, MPFormModel, MsNewGetDados, MsGetDados, EnchoiceBar, Modelo3
