/** User-facing names for the API enums. */

import type {
  AccountKind,
  AnswerValue,
  ArcaClass,
  AssetLifecycle,
  AssetPurpose,
  AssetType,
  ChecklistProfile,
  ContributionPlanStatus,
  CorporateEventKind,
  EarningKind,
  FixedIncomeIndexer,
  FixedIncomeInstrumentKind,
  FixedIncomeLiquidity,
  IntraClassStrategy,
  OfferIndexer,
  QuoteFreshness,
  TaxRegime,
  TransactionKind,
} from "../api/types";

export const ARCA_CLASSES: ArcaClass[] = ["ACOES", "REAL_ESTATE", "CAIXA", "ATIVOS_INTERNACIONAIS"];

export const ARCA_LABELS: Record<ArcaClass, string> = {
  ACOES: "Ações",
  REAL_ESTATE: "Real Estate",
  CAIXA: "Caixa",
  ATIVOS_INTERNACIONAIS: "Ativos internacionais",
};

export const ASSET_TYPES: AssetType[] = [
  "STOCK_BR",
  "ETF_BR",
  "FII",
  "BDR",
  "STOCK_INTL",
  "ETF_INTL",
  "REIT",
  "CRYPTO",
  "FIXED_INCOME",
  "TREASURY",
  "CASH",
];

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  STOCK_BR: "Ação B3",
  ETF_BR: "ETF B3",
  FII: "Fundo imobiliário",
  BDR: "BDR",
  STOCK_INTL: "Ação exterior",
  ETF_INTL: "ETF exterior",
  REIT: "REIT",
  CRYPTO: "Criptoativo",
  FIXED_INCOME: "Renda fixa",
  TREASURY: "Tesouro Direto",
  CASH: "Caixa",
};

export const FIXED_INCOME_TYPES: AssetType[] = ["FIXED_INCOME", "TREASURY"];

export const PURPOSE_LABELS: Record<AssetPurpose, string> = {
  ARCA: "Carteira ARCA",
  EMERGENCY_RESERVE: "Reserva de emergência",
  OTHER: "Outro objetivo",
};

export const LIFECYCLE_LABELS: Record<AssetLifecycle, string> = {
  WATCHLIST: "Observação",
  ELIGIBLE: "Elegível",
  HELD: "Em carteira",
  REVIEW: "Em revisão",
  ARCHIVED: "Arquivado",
};

export const LIFECYCLE_TONES: Record<AssetLifecycle, string> = {
  WATCHLIST: "neutral",
  ELIGIBLE: "info",
  HELD: "success",
  REVIEW: "warning",
  ARCHIVED: "neutral",
};

export const PROFILES: ChecklistProfile[] = [
  "STOCK",
  "BANK",
  "FII_BRICK",
  "FII_PAPER",
  "ETF",
  "INTL_STOCK",
  "CRYPTO",
  "FIXED_INCOME",
];

export const PROFILE_LABELS: Record<ChecklistProfile, string> = {
  STOCK: "Ação",
  BANK: "Banco",
  FII_BRICK: "FII de tijolo",
  FII_PAPER: "FII de papel",
  ETF: "ETF",
  INTL_STOCK: "Ação internacional",
  CRYPTO: "Cripto",
  FIXED_INCOME: "Renda fixa",
};

export const ANSWER_LABELS: Record<AnswerValue, string> = { YES: "Sim", NO: "Não", NA: "Não se aplica" };

export const VERDICT_LABELS: Record<string, string> = {
  DISCOUNTED: "Descontado",
  FAIR: "Preço justo",
  EXPENSIVE: "Caro",
  UNDEFINED: "Sem dados",
  NOT_APPLICABLE: "Não se aplica",
};

export const VERDICT_TONES: Record<string, string> = {
  DISCOUNTED: "success",
  FAIR: "info",
  EXPENSIVE: "danger",
  UNDEFINED: "neutral",
  NOT_APPLICABLE: "neutral",
};

export const RECOMMENDATION_LABELS: Record<string, string> = {
  APTO: "Apto",
  REVISAR: "Revisar",
  INCOMPLETO: "Incompleto",
  DESATIVADO: "Desativado",
};

export const FRESHNESS_LABELS: Record<QuoteFreshness, string> = {
  LIVE: "Ao vivo",
  CACHED: "Cache",
  FALLBACK: "Sem cotação",
  CURVE: "Curva",
  MANUAL: "Manual",
};

export const TRADE_LABELS: Record<TransactionKind, string> = { BUY: "Compra", SELL: "Venda" };

export const EARNING_KINDS: EarningKind[] = ["DIVIDEND", "JCP", "FII_YIELD", "FIXED_INCOME_COUPON", "RESTITUTION"];

export const EARNING_LABELS: Record<EarningKind, string> = {
  DIVIDEND: "Dividendo",
  JCP: "JCP",
  FII_YIELD: "Rendimento",
  FIXED_INCOME_COUPON: "Cupom",
  RESTITUTION: "Restituição de capital",
};

export const EVENT_KINDS: CorporateEventKind[] = ["SPLIT", "REVERSE_SPLIT", "BONUS"];

export const EVENT_LABELS: Record<CorporateEventKind, string> = {
  SPLIT: "Desdobramento",
  REVERSE_SPLIT: "Grupamento",
  BONUS: "Bonificação",
};

export const STRATEGY_LABELS: Record<IntraClassStrategy, string> = {
  CERRADO: "Pela nota do checklist",
  MANUAL_WEIGHT: "Pesos manuais",
  EQUAL_WEIGHT: "Pesos iguais",
};

export const PLAN_STATUS_LABELS: Record<ContributionPlanStatus, string> = {
  DRAFT: "Rascunho",
  CONFIRMED: "Confirmado",
  DISCARDED: "Descartado",
};

export const ACCOUNT_KIND_LABELS: Record<AccountKind, string> = {
  BROKER: "Corretora",
  BANK: "Banco",
  EXCHANGE: "Exchange",
  OTHER: "Outra",
};

export const INSTRUMENT_KINDS: FixedIncomeInstrumentKind[] = [
  "CDB",
  "LCI",
  "LCA",
  "CRI",
  "CRA",
  "DEBENTURE",
  "TESOURO_SELIC",
  "TESOURO_IPCA",
  "TESOURO_PRE",
  "SAVINGS_BOX",
];

export const INSTRUMENT_LABELS: Record<FixedIncomeInstrumentKind, string> = {
  CDB: "CDB",
  LCI: "LCI",
  LCA: "LCA",
  CRI: "CRI",
  CRA: "CRA",
  DEBENTURE: "Debênture",
  TESOURO_SELIC: "Tesouro Selic",
  TESOURO_IPCA: "Tesouro IPCA+",
  TESOURO_PRE: "Tesouro Prefixado",
  SAVINGS_BOX: "Caixinha / conta remunerada",
};

export const INDEXERS: FixedIncomeIndexer[] = ["CDI", "SELIC", "IPCA", "PRE"];

export const INDEXER_HINTS: Record<FixedIncomeIndexer, string> = {
  CDI: "% do CDI (ex.: 110)",
  SELIC: "% da Selic (ex.: 100)",
  IPCA: "Taxa real ao ano (ex.: 6,2)",
  PRE: "Taxa ao ano (ex.: 12,5)",
};

export const LIQUIDITY_LABELS: Record<FixedIncomeLiquidity, string> = {
  DAILY: "Diária",
  AT_MATURITY: "No vencimento",
};

export const SEVERITY_TONES: Record<string, string> = {
  CRITICAL: "danger",
  WARNING: "warning",
  INFO: "info",
};

export const TAX_REGIME_LABELS: Record<TaxRegime, string> = {
  FIXED_INCOME_REGRESSIVE: "IR regressivo da renda fixa",
  FIXED_INCOME_EXEMPT: "Renda fixa isenta",
  IOF_REGRESSIVE: "IOF regressivo",
  STOCK_SWING_TRADE: "Ganho na venda de ações",
  ETF_BDR_SWING_TRADE: "Ganho na venda de ETFs e BDRs",
  FII_CAPITAL_GAIN: "Ganho na venda de cotas de FII",
  FII_DISTRIBUTION: "Rendimentos de FII",
  DIVIDEND_WITHHOLDING: "Dividendos",
  JCP_WITHHOLDING: "Juros sobre capital próprio",
  FOREIGN_ANNUAL: "Aplicações no exterior",
  CRYPTO_CAPITAL_GAIN: "Ganho com criptoativos",
};

export const OFFER_INDEXER_LABELS: Record<OfferIndexer, string> = {
  CDI_PERCENT: "% do CDI",
  CDI_SPREAD: "CDI + taxa",
  IPCA_SPREAD: "IPCA + taxa",
  PRE: "Prefixado",
};

export const OFFER_INDEXER_HINTS: Record<OfferIndexer, string> = {
  CDI_PERCENT: "% do CDI (ex.: 110)",
  CDI_SPREAD: "Taxa acima do CDI ao ano (ex.: 1,5)",
  IPCA_SPREAD: "Taxa real ao ano (ex.: 6,5)",
  PRE: "Taxa ao ano (ex.: 12,5)",
};

export const SCENARIO_LABELS: Record<string, string> = {
  LOW: "Juros em queda",
  BASE: "Base",
  HIGH: "Juros em alta",
};
