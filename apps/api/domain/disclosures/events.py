"""Event taxonomy of the CVM disclosures (Phase 42.4): which documents are events, and of what kind.

The IPE gives, per document, a category, a type, a species and a free subject written by the
company. A relevant fact (Fato Relevante) has no type or species: its subject is all there is.
So the class comes from rules, in order, on the plain text (lower case, no accents) of the
category, the type and the subject; the first rule that matches wins. No language model reads
the documents (decision 42.0-6).

Only some documents are events: relevant facts, changes of relevant holdings (art. 12),
shareholder notices about dividends, and filings of companies under judicial recovery. The rest
(meetings, routine filings, results presentations, monthly insider reports) are not, and keep no
class. A relevant fact that matches no rule is OTHER: the share of OTHER says how much the
keywords cover.
"""

from __future__ import annotations

import re

from domain.disclosures.statements import plain

RESTRUCTURING = "RESTRUCTURING"
TAKEOVER = "TAKEOVER"
BUYBACK = "BUYBACK"
DIVIDENDS = "DIVIDENDS"
EQUITY_OFFERING = "EQUITY_OFFERING"
DEBT_ISSUANCE = "DEBT_ISSUANCE"
DIVESTMENT = "DIVESTMENT"
ACQUISITION = "ACQUISITION"
MANAGEMENT = "MANAGEMENT"
GUIDANCE = "GUIDANCE"
RATING_DOWN = "RATING_DOWN"
LITIGATION = "LITIGATION"
INCIDENT = "INCIDENT"
OPERATING_DATA = "OPERATING_DATA"
CAPITAL_CHANGE = "CAPITAL_CHANGE"
PROJECT = "PROJECT"
CLARIFICATION = "CLARIFICATION"
GOVERNANCE = "GOVERNANCE"
CONTRACT = "CONTRACT"
STAKE_CHANGE = "STAKE_CHANGE"
OTHER = "OTHER"

EVENT_LABELS = {
    RESTRUCTURING: "Recuperação judicial ou reestruturação de dívida",
    TAKEOVER: "OPA ou mudança de controle",
    BUYBACK: "Recompra de ações",
    DIVIDENDS: "Dividendos e JCP",
    EQUITY_OFFERING: "Emissão de ações (diluição)",
    DEBT_ISSUANCE: "Emissão de dívida",
    DIVESTMENT: "Desinvestimento ou venda de ativos",
    ACQUISITION: "Aquisição, fusão ou incorporação",
    MANAGEMENT: "Mudança na administração",
    GUIDANCE: "Projeções e guidance",
    RATING_DOWN: "Rebaixamento de rating",
    LITIGATION: "Litígio, fiscal, multa ou investigação",
    INCIDENT: "Acidente ou paralisação",
    OPERATING_DATA: "Resultados e prévias operacionais",
    CAPITAL_CHANGE: "Grupamento, desdobramento ou redução de capital",
    PROJECT: "Projetos e investimentos",
    CLARIFICATION: "Esclarecimento sobre notícia ou carta de acionista",
    GOVERNANCE: "Assembleia, estatuto ou acordo de acionistas",
    CONTRACT: "Contrato relevante",
    STAKE_CHANGE: "Mudança de participação relevante",
    OTHER: "Outros fatos relevantes",
}

_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        RESTRUCTURING,
        re.compile(
            r"recuperacao (judicial|extrajudicial)|reestrutura\w* (de|da|das) (sua )?divida|"
            r"plano de recuperacao|\bprj\b|falencia|vencimento antecipado|\bwaiver\b|"
            r"inadimplemento|standstill|reperfilamento|chapter (11|15)|tutela cautelar|credores|"
            r"recuperacao (judicial|extrajudicial)"
        ),
    ),
    (
        TAKEOVER,
        re.compile(
            r"\bopa\b|oferta publica (unificada )?de aquisicao|fechamento de capital|"
            r"(alienacao|transferencia|mudanca|aquisicao) (do|de) controle|"
            r"cancelamento de registro de companhia aberta|assessor(es)? financeiro|"
            r"(alternativas|oportunidades) estrategicas|sondagens|manifestac\w* de interesse"
        ),
    ),
    (
        BUYBACK,
        re.compile(
            r"recompra(?! de debentures)|aquisicao de acoes de (sua )?(propria )?emissao|"
            r"(acoes|emissao) da propria companhia|negociacao com acoes de propria emissao"
        ),
    ),
    (
        DIVIDENDS,
        re.compile(
            r"dividendo|juros (sobre|s/) ?(o )?capital|\bjcp\b|proventos|capital proprio|"
            r"remuneracao (complementar )?(aos|dos|ao) acionistas?"
        ),
    ),
    (
        CAPITAL_CHANGE,
        re.compile(
            r"grupamento|desdobramento|\bsplit\b|inplit|reducao (do|de) capital|"
            r"cancelamento (das|de) acoes|cotacao minima|enquadramento da cotacao|"
            r"bonificacao em acoes"
        ),
    ),
    (
        EQUITY_OFFERING,
        re.compile(
            r"oferta publica (primaria|subsequente|de distribuicao (primaria )?de acoes)|"
            r"follow.?on|aumento de capital|subscricao (privada|publica)?|"
            r"emissao de (novas )?acoes|\bipo\b|oferta (restrita|publica) de acoes"
        ),
    ),
    (
        DEBT_ISSUANCE,
        re.compile(
            r"debentures?|notas? promissorias?|notas comerciais|\bbonds?\b|"
            r"titulos de divida|\bnotes\b|\bcri\b|\bcra\b|captacao|emprestimo|financiamento|"
            r"letras? financeiras?|debenturistas|\bagd\b|recompra de debentures"
        ),
    ),
    (
        EQUITY_OFFERING,
        re.compile(
            r"oferta publica|distribuicao publica|integralizacao de capital|oferta (de acoes|"
            r"profissional)|preco da oferta|anuncio (de|da) oferta|aporte de capital|"
            r"capitalizacao|\bemissoes\b"
        ),
    ),
    (ACQUISITION, re.compile(r"reorganizacao societaria|incorporacao, cisao ou fusao")),
    (
        DIVESTMENT,
        re.compile(
            r"desinvestimento|alienacao|venda (de|da|do|dos|das) (participacao|ativo|subsidiaria|"
            r"unidade|operac|carteira|lote|imove|empresa|controlada)|conclusao da venda|"
            r"\bcisao\b|spin.?off|desmembramento"
        ),
    ),
    (
        ACQUISITION,
        re.compile(
            r"aquisicao|incorporacao|\bfusao\b|combinacao de negocios|joint.?venture|"
            r"associacao (com|entre)|proposta vinculante|\bspa\b|scheme of arrangement|"
            r"investimento na|compra e venda de acoes|"
            r"\bmou\b|memorando de entendimento|compra de (participacao|ativos|empresa)|"
            r"reorganizacao societaria"
        ),
    ),
    (
        MANAGEMENT,
        re.compile(
            r"(renuncia|eleicao|eleito|nomeacao|substituicao|sucessao|desligamento|novos?|novas?|"
            r"alterac\w*|mudanc\w*)\b.{0,40}(diretor|presiden|\bceo\b|\bcfo\b|"
            r"conselh\w* de administracao|membro do conselho|alta administracao)|"
            r"(diretor|presiden|\bceo\b|\bcfo\b).{0,30}(renuncia|deixa|desligamento|substitu)|"
            r"transicao na (alta )?administracao|remanejamento|"
            r"posse de diretor"
        ),
    ),
    (GUIDANCE, re.compile(r"projec|guidance|estimativas?|previsao de resultado|perspectivas")),
    (RATING_DOWN, re.compile(r"rebaix|downgrade|perspectiva negativa|rating negativo")),
    (
        LITIGATION,
        re.compile(
            r"arbitra|acao (judicial|civil|coletiva)|processo (judicial|administrativo)|"
            r"\bmulta\b|autuac|auto de infracao|condenac|decisao judicial|tribunal|\bstf\b|"
            r"\bstj\b|investigac|leniencia|\bcade\b|\btcu\b|\bliminar|sentenca|denuncia|"
            r"tribut|fiscal|receita federal|arrolamento|\bcfem\b|contingenc|"
            r"processos? judicia|desapropria|\bicms\b"
        ),
    ),
    (
        INCIDENT,
        re.compile(
            r"acidente|incendio|paralisa|interrupcao (da|das|de|do) (operac|producao|atividade|"
            r"fornecimento|planta|unidade)|incidente|\bgreve\b|rompimento|explosao|"
            r"vazamento|desastre|ataque (hacker|cibernetico)|ciberneti|hibernac|"
            r"retorno (parcial )?das operacoes"
        ),
    ),
    (
        OPERATING_DATA,
        re.compile(
            r"previa operacional|dados operacionais|resultados? (preliminar|operaciona)|"
            r"producao e vendas|informacoes operacionais|reservas|resultados? financeiros?|"
            r"divulgacao (dos|de) resultados?|resultados? (do|de|dos) \d|relatorio operacional|"
            r"atraso (na|no|do|da) (entrega|divulgacao|\d)|\bitr\b|\bdfp\b|"
            r"adiamento da divulgacao|refazimento|reapresentacao das demonstracoes"
        ),
    ),
    (
        CLARIFICATION,
        re.compile(
            r"noticia|esclarec|cartas? recebidas?|correspondencia|recebimento de (carta|"
            r"comunicado|informacao)|comunicado (de|do) acionista|midia|imprensa|rumor"
        ),
    ),
    (
        GOVERNANCE,
        re.compile(
            r"assembleia|estatuto|acordo de acionistas|convocacao|\bage\b|\bago\b|"
            r"conselho fiscal|politica de|formador de mercado|mercado de negociacao|"
            r"oficio b3|decisao b3|direito de recesso"
        ),
    ),
    (
        PROJECT,
        re.compile(
            r"projeto|start.?up|retomada|descoberta|teste de formacao|poco|expansao|"
            r"investimento em|nova (fabrica|planta|unidade)|plano estrategico|capacidade|"
            r"permuta|sinergia|constituicao (de|da) (subsidiaria|empresa|sociedade)"
        ),
    ),
    (
        CONTRACT,
        re.compile(
            r"contrato|acordo|celebracao|parceria|licitacao|concessao|leilao|vencedor|"
            r"reajuste tarifario|revisao tarifaria|autorizacao"
        ),
    ),
]

_RELEVANT_FACT = "fato relevante"
_STAKE = re.compile(r"participacao acionaria \(art\. 12")
_RECOVERY = re.compile(r"recuperacao judicial ou extrajudicial")
_SHAREHOLDER_NOTICE = "aviso aos acionistas"


def classify(category: str, doc_type: str, subject: str) -> str | None:
    """The event class of a document, or None when it is not an event."""
    cat = plain(category)
    kind = plain(doc_type)
    text = plain(subject)
    if _STAKE.search(kind):
        return STAKE_CHANGE
    if _RECOVERY.search(cat):
        return RESTRUCTURING
    if cat.startswith(_SHAREHOLDER_NOTICE):
        return (
            DIVIDENDS
            if re.search(r"dividendo|juros sobre (o )?capital|\bjcp\b|proventos", text)
            else None
        )
    if not cat.startswith(_RELEVANT_FACT):
        return None
    for name, pattern in _RULES:
        if pattern.search(text):
            return name
    return OTHER
