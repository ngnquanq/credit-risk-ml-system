from abc import ABC, abstractmethod

class ScoringGateway(ABC):
    @abstractmethod
    async def publish_for_scoring(self, application_id: str) -> None:
        """
        Publish the application ID to a message broker (Kafka) for scoring.
        The actual scoring happens asynchronously by serving pods consuming from the queue.
        """
        pass
