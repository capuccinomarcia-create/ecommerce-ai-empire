"""Agentes especializados do E-COMMERCE AI EMPIRE."""

from agents.automation import AutomationAgent
from agents.ceo import CEOAgent
from agents.content_intelligence import ContentIntelligenceAgent
from agents.customer import CustomerAgent
from agents.financial import FinancialAgent
from agents.market_analyst import MarketAnalystAgent
from agents.marketing import MarketingAgent
from agents.marketplace import MarketplaceManagerAgent
from agents.product_hunter import ProductHunterAgent
from agents.seo import SEOAgent
from agents.supplier import SupplierHunterAgent
from agents.video_creator import VideoCreatorAgent

AGENT_CLASSES = {
    "ceo": CEOAgent,
    "product_hunter": ProductHunterAgent,
    "market_analyst": MarketAnalystAgent,
    "marketplace_manager": MarketplaceManagerAgent,
    "financial": FinancialAgent,
    "marketing": MarketingAgent,
    "video_creator": VideoCreatorAgent,
    "seo": SEOAgent,
    "supplier_hunter": SupplierHunterAgent,
    "customer": CustomerAgent,
    "automation": AutomationAgent,
    "content_intelligence": ContentIntelligenceAgent,
}


def build_agents() -> dict:
    """Instancia todos os agentes (stateless; recebem contexto em run())."""
    return {key: cls() for key, cls in AGENT_CLASSES.items()}


__all__ = ["AGENT_CLASSES", "build_agents"]
