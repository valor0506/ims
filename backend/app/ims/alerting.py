from abc import ABC, abstractmethod
from dataclasses import dataclass
import asyncio

@dataclass
class Alert:
    """Alert data transfer object"""
    work_item_id: str
    component_id: str
    severity: str
    message: str

class AlertStrategy(ABC):
    """
    Strategy Pattern: Different alert behaviors for different severities.
    Abstract base class - all strategies must implement execute().
    """
    
    @property
    @abstractmethod
    def priority(self) -> str:
        pass
    
    @abstractmethod
    async def execute(self, alert: Alert) -> None:
        pass

class PagerDutyStrategy(AlertStrategy):
    """P0: Page on-call engineer immediately"""
    priority = "critical"
    
    async def execute(self, alert: Alert) -> None:
        # In production: call PagerDuty Events API v2
        # For assignment: simulate with print
        print(f"🚨 [PAGERDUTY] PAGE ON-CALL: {alert.component_id} | {alert.message}")
        await asyncio.sleep(0.1)  # Simulate API latency

class SlackStrategy(AlertStrategy):
    """P1/P2: Slack notification to channel"""
    priority = "high"
    
    async def execute(self, alert: Alert) -> None:
        print(f"📢 [SLACK] #{alert.component_id}: {alert.message}")
        await asyncio.sleep(0.05)

class LogStrategy(AlertStrategy):
    """P3: Log only, no notification"""
    priority = "low"
    
    async def execute(self, alert: Alert) -> None:
        print(f"📝 [LOG] {alert.component_id}: {alert.message}")

class AlertRouter:
    """
    Context in Strategy Pattern.
    Routes alerts to appropriate strategy based on severity.
    """
    
    # Registry of strategies
    STRATEGIES = {
        "P0": PagerDutyStrategy,
        "P1": SlackStrategy,
        "P2": SlackStrategy,
        "P3": LogStrategy
    }
    
    def get_strategy(self, severity: str) -> AlertStrategy:
        """Factory method: returns strategy instance for severity"""
        strategy_class = self.STRATEGIES.get(severity, LogStrategy)
        return strategy_class()
    
    async def dispatch(self, alert: Alert) -> None:
        """Execute alert through appropriate strategy"""
        strategy = self.get_strategy(alert.severity)
        await strategy.execute(alert)