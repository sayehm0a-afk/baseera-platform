import logging
import heapq
from abc import ABC, abstractmethod
from typing import Any, List, Tuple

logger = logging.getLogger(__name__)


class IPriorityQueue(ABC):
    """واجهة مجردة لقائمة الانتظار ذات الأولوية (Priority Queue).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لقائمة
    الانتظار ذات الأولوية.
    """

    @abstractmethod
    async def put(self, item: Any, priority: int = 0) -> None:
        """يضيف عنصرًا إلى قائمة الانتظار ذات الأولوية.

        Args:
            item (Any): العنصر المراد إضافته.
            priority (int): أولوية العنصر (افتراضي 0، حيث الأرقام الأعلى
                تعني أولوية أعلى).
        """
        raise NotImplementedError

    @abstractmethod
    async def get(self) -> Any:
        """يسترد العنصر ذو الأولوية القصوى من قائمة الانتظار.

        Returns:
            Any: العنصر ذو الأولوية القصوى.

        Raises:
            IndexError: إذا كانت قائمة الانتظار فارغة.
        """
        raise NotImplementedError

    @abstractmethod
    async def qsize(self) -> int:
        """يعيد عدد العناصر في قائمة الانتظار.

        Returns:
            int: عدد العناصر.
        """
        raise NotImplementedError

    @abstractmethod
    async def empty(self) -> bool:
        """يتحقق مما إذا كانت قائمة الانتظار فارغة.

        Returns:
            bool: True إذا كانت قائمة الانتظار فارغة، False بخلاف ذلك.
        """
        raise NotImplementedError


class PriorityQueue(IPriorityQueue):
    """تنفيذ قائمة الانتظار ذات الأولوية (Priority Queue).

    تستخدم heapq للحفاظ على ترتيب الأولوية.
    """

    def __init__(self) -> None:
        self._queue: List[Tuple[int, int, Any]] = []  # (priority, entry_id,
        # item)
        self._entry_id = 0
        logger.info("PriorityQueue instance created.")

    async def put(self, item: Any, priority: int = 0) -> None:
        # heapq هو min-heap، لذا نستخدم أولوية سالبة لتمثيل الأولوية الأعلى
        # كقيمة أصغر.
        # entry_id يستخدم لكسر التعادل بين العناصر ذات الأولوية المتساوية.
        heapq.heappush(self._queue, (-priority, self._entry_id, item))
        self._entry_id += 1
        logger.debug("Item added to PriorityQueue with priority %d.", priority)

    async def get(self) -> Any:
        if await self.empty():
            raise IndexError("get from an empty priority queue")
        _, _, item = heapq.heappop(self._queue)
        logger.debug("Item retrieved from PriorityQueue.")
        return item

    async def qsize(self) -> int:
        return len(self._queue)

    async def empty(self) -> bool:
        return not self._queue
