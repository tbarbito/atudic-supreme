#Include "Protheus.ch"
#Include "RESTFul.ch"

/*/{Protheus.doc} ZATUREF
Servico REST para forcar TcRefresh em tabelas apos equalizacao
do dicionario via AtuDIC (Equalizador de Dicionario).

Quando o AtuDIC cria campos diretamente no banco (ALTER TABLE + INSERT SX3
+ INSERT TOP_FIELD), o DBAccess mantem seu cache interno desatualizado.
Este endpoint forca o TcRefresh + DbUseArea para que o DBAccess reconstrua
o mapeamento de campos, permitindo que as rotinas do Protheus gravem nos
campos novos imediatamente � sem reiniciar DBAccess ou abrir pelo APSDU.

@author  Barbito (Tiago Barbieri)
@since   20/03/2026
@version 1.0
/*/

WSRESTFUL ZATUREF DESCRIPTION "AtuDIC - TcRefresh pos-equalizacao"

    WSDATA cBody AS STRING

    WSMETHOD POST DESCRIPTION "Forca TcRefresh nas tabelas informadas"

END WSRESTFUL


WSMETHOD POST WSSERVICE ZATUREF

Local cBody     := ""
Local oJson     := Nil
Local aTables   := {}
Local cTable    := ""
Local aResults  := {}
Local nI        := 0
Local cAlias    := ""
Local lOk       := .F.
Local cError    := ""
Local cSvAlias  := Alias()

// Ler o body da requisicao
cBody := Self:GetContent()

If Empty(cBody)
    Self:SetResponse('{"success": false, "error": "Payload JSON vazio"}')
    SetRestFault(400, "Payload JSON vazio")
    Return .F.
EndIf

// Parse do JSON
oJson := JsonObject():New()
If oJson:FromJson(cBody) <> Nil
    Self:SetResponse('{"success": false, "error": "JSON invalido"}')
    SetRestFault(400, "JSON invalido")
    Return .F.
EndIf

// Ler array de tabelas
aTables := oJson:GetJsonObject("tables")
If aTables == Nil .Or. Len(aTables) == 0
    Self:SetResponse('{"success": false, "error": "Array tables vazio ou ausente"}')
    SetRestFault(400, "Array tables vazio ou ausente")
    Return .F.
EndIf

// Processar cada tabela
For nI := 1 To Len(aTables)
    cTable := Upper(AllTrim(aTables[nI]))
    cAlias := "ZREF" + StrZero(nI, 3)
    lOk    := .F.
    cError := ""

    BEGIN SEQUENCE

        // Forcar DBAccess a descartar cache de metadados da tabela
        TcRefresh(cTable)

        // Abrir a tabela para forcar reconstrucao do mapeamento interno
        DbUseArea(.T., "TOPCONN", cTable, cAlias, .T., .T.)

        If !NetErr()
            lOk := .T.
            DbSelectArea(cAlias)
            DbCloseArea()
        Else
            cError := "NetErr ao abrir " + cTable
        EndIf

    RECOVER
        cError := "Excecao ao processar " + cTable

    END SEQUENCE

    Aadd(aResults, '{"table": "' + cTable + '", "refreshed": ' + If(lOk, "true", "false") + ;
        If(!Empty(cError), ', "error": "' + cError + '"', "") + "}")
Next nI

// Restaurar area de trabalho original
If !Empty(cSvAlias) .And. Select(cSvAlias) > 0
    DbSelectArea(cSvAlias)
EndIf

// Montar resposta JSON
Self:SetResponse('{"success": true, "results": [' + _ArrayJoin(aResults, ",") + "]}")

Return .T.


/*/{Protheus.doc} _ArrayJoin
Junta elementos de um array em uma string separada por delimitador.
Funcao auxiliar local para montar o JSON de resposta.

@param aArr   Array de strings
@param cSep   Separador

@return cResult String concatenada
@author  Barbito
@since   20/03/2026
/*/
Static Function _ArrayJoin(aArr, cSep)
Local cResult := ""
Local nJ      := 0

For nJ := 1 To Len(aArr)
    If nJ > 1
        cResult += cSep
    EndIf
    cResult += aArr[nJ]
Next nJ

Return cResult
