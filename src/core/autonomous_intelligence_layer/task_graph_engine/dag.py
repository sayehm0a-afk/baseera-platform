from collections import defaultdict, deque
from typing import Dict, List, Set, Any, Optional
import uuid
from .node import Node

class DAG:
    """
    يمثل الرسم البياني الموجه غير الدوري (DAG) للمهام.

    يدير العقد (المهام) والتبعيات بينها.
    """

    def __init__(self, dag_id: Optional[str] = None):
        """
        يهيئ مثيلًا جديدًا للرسم البياني الموجه غير الدوري.
        """
        self.id: str = dag_id if dag_id else str(uuid.uuid4())
        self.nodes: Dict[str, Node] = {}
        self.adj: Dict[str, List[str]] = defaultdict(list)  # قائمة التجاور: node_id -> [dependent_node_ids]
        self.in_degree: Dict[str, int] = defaultdict(int)  # درجة الدخول لكل عقدة

    def add_node(self, node: Node) -> None:
        """
        يضيف عقدة إلى الرسم البياني.

        Args:
            node (Node): العقدة المراد إضافتها.

        Raises:
            ValueError: إذا كانت العقدة موجودة بالفعل.
        """
        if not isinstance(node, Node):
            raise ValueError("العقدة يجب أن تكون من نوع Node.")
        if node.id in self.nodes:
            raise ValueError(f"العقدة ذات المعرف {node.id} موجودة بالفعل في الرسم البياني.")
        self.nodes[node.id] = node
        self.in_degree[node.id] = 0 # تهيئة درجة الدخول للعقدة الجديدة

    def add_edge(self, from_node_id: str, to_node_id: str) -> None:
        """
        يضيف حافة موجهة من عقدة المصدر إلى عقدة الوجهة.

        Args:
            from_node_id (str): معرف عقدة المصدر.
            to_node_id (str): معرف عقدة الوجهة.

        Raises:
            ValueError: إذا كانت أي من العقدتين غير موجودة، أو إذا كانت الحافة ستنشئ دورة.
        """
        if from_node_id not in self.nodes:
            raise ValueError(f"عقدة المصدر ذات المعرف {from_node_id} غير موجودة.")
        if to_node_id not in self.nodes:
            raise ValueError(f"عقدة الوجهة ذات المعرف {to_node_id} غير موجودة.")
        if to_node_id in self.adj[from_node_id]:
            # الحافة موجودة بالفعل، لا تفعل شيئًا
            return

        self.adj[from_node_id].append(to_node_id)
        self.in_degree[to_node_id] += 1

        if self.has_cycle():
            # التراجع عن إضافة الحافة إذا تسببت في دورة
            self.adj[from_node_id].pop()
            self.in_degree[to_node_id] -= 1
            raise ValueError(f"إضافة حافة من {from_node_id} إلى {to_node_id} ستنشئ دورة في الرسم البياني.")

    def get_dependencies(self, node_id: str) -> List[Node]:
        """
        يحصل على العقد التي تعتمد عليها العقدة المحددة (أي العقد التي يجب تنفيذها قبلها).

        Args:
            node_id (str): معرف العقدة.

        Returns:
            List[Node]: قائمة بالعقد التي تعتمد عليها العقدة المحددة.

        Raises:
            ValueError: إذا كانت العقدة غير موجودة.
        """
        if node_id not in self.nodes:
            raise ValueError(f"العقدة ذات المعرف {node_id} غير موجودة.")

        # للحصول على التبعيات، نحتاج إلى العقد التي تشير إلى node_id
        # هذا يتطلب عكس الرسم البياني أو تتبع السوابق
        # حاليًا، adj يمثل التوابع (successors)، وليس السوابق (predecessors)
        # يمكننا تعديل بنية البيانات أو حسابها ديناميكيًا
        dependencies = []
        for n_id, successors in self.adj.items():
            if node_id in successors:
                dependencies.append(self.nodes[n_id])
        return dependencies

    def get_successors(self, node_id: str) -> List[Node]:
        """
        يحصل على العقد التي تعتمد على العقدة المحددة (أي العقد التي يمكن تنفيذها بعدها).

        Args:
            node_id (str): معرف العقدة.

        Returns:
            List[Node]: قائمة بالعقد التي تعتمد على العقدة المحددة.

        Raises:
            ValueError: إذا كانت العقدة غير موجودة.
        """
        if node_id not in self.nodes:
            raise ValueError(f"العقدة ذات المعرف {node_id} غير موجودة.")
        return [self.nodes[successor_id] for successor_id in self.adj[node_id]]

    def has_cycle(self) -> bool:
        """
        يكتشف ما إذا كان الرسم البياني يحتوي على دورة باستخدام DFS.

        Returns:
            bool: True إذا تم العثور على دورة، False بخلاف ذلك.
        """
        visited: Set[str] = set()
        recursion_stack: Set[str] = set()

        for node_id in self.nodes:
            if node_id not in visited:
                if self._dfs_cycle_check(node_id, visited, recursion_stack):
                    return True
        return False

    def _dfs_cycle_check(self, node_id: str, visited: Set[str], recursion_stack: Set[str]) -> bool:
        """
        وظيفة مساعدة لـ DFS لاكتشاف الدورات.
        """
        visited.add(node_id)
        recursion_stack.add(node_id)

        for neighbor_id in self.adj[node_id]:
            if neighbor_id not in visited:
                if self._dfs_cycle_check(neighbor_id, visited, recursion_stack):
                    return True
            elif neighbor_id in recursion_stack:
                return True

        recursion_stack.remove(node_id)
        return False

    def topological_sort(self) -> List[Node]:
        """
        يقوم بالفرز الطوبولوجي للعقد في الرسم البياني.

        Returns:
            List[Node]: قائمة مرتبة طوبولوجيًا بالعقد.

        Raises:
            ValueError: إذا كان الرسم البياني يحتوي على دورة.
        """
        if self.has_cycle():
            raise ValueError("لا يمكن إجراء الفرز الطوبولوجي على رسم بياني يحتوي على دورة.")

        q = deque()
        current_in_degree = self.in_degree.copy()
        sorted_nodes: List[Node] = []

        for node_id in self.nodes:
            if current_in_degree[node_id] == 0:
                q.append(node_id)

        while q:
            node_id = q.popleft()
            sorted_nodes.append(self.nodes[node_id])

            for neighbor_id in self.adj[node_id]:
                current_in_degree[neighbor_id] -= 1
                if current_in_degree[neighbor_id] == 0:
                    q.append(neighbor_id)

        if len(sorted_nodes) != len(self.nodes):
            # هذا الشرط يجب أن يكون صحيحًا فقط إذا كان هناك دورة، ولكننا نتحقق من الدورات مسبقًا.
            # ومع ذلك، هو فحص إضافي للتأكد.
            raise ValueError("الرسم البياني يحتوي على دورة، لا يمكن إجراء الفرز الطوبولوجي.")

        return sorted_nodes

    def __len__(self) -> int:
        return len(self.nodes)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.nodes

    def __repr__(self) -> str:
        nodes_str = ", ".join(self.nodes.keys())
        edges_str = ", ".join([f"{u}->{v}" for u, vs in self.adj.items() for v in vs])
        return f"DAG(nodes=[{nodes_str}], edges=[{edges_str}])"
