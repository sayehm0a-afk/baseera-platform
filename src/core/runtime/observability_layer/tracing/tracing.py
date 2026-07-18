from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import uuid
import time

class ISpan(ABC):
    @abstractmethod
    def set_attribute(self, key: str, value: Any):
        """
        يضبط سمة (attribute) لهذا الامتداد (span).
        """
        pass

    @abstractmethod
    def record_exception(self, exception: Exception, attributes: Optional[Dict[str, Any]] = None):
        """
        يسجل استثناءً (exception) لهذا الامتداد.
        """
        pass

    @abstractmethod
    def end(self):
        """
        ينهي هذا الامتداد.
        """
        pass

class ITracer(ABC):
    @abstractmethod
    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> ISpan:
        """
        يبدأ امتدادًا جديدًا (span).
        """
        pass

    @abstractmethod
    def current_span(self) -> Optional[ISpan]:
        """
        يعيد الامتداد الحالي (current span) من السياق.
        """
        pass

    @abstractmethod
    def set_current_span(self, span: ISpan):
        """
        يضبط الامتداد الحالي في السياق.
        """
        pass

class Span(ISpan):
    def __init__(self, name: str, tracer: 'Tracer', attributes: Optional[Dict[str, Any]] = None):
        self.span_id = str(uuid.uuid4())
        self.trace_id = str(uuid.uuid4()) # For simplicity, new trace for each span for now
        self.name = name
        self.start_time = time.time()
        self.end_time = None
        self.attributes = attributes if attributes is not None else {}
        self.events = []
        self.tracer = tracer


    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value


    def record_exception(self, exception: Exception, attributes: Optional[Dict[str, Any]] = None):
        event_attributes = {"event.name": "exception", "exception.type": type(exception).__name__, "exception.message": str(exception)}
        if attributes:
            event_attributes.update(attributes)
        self.events.append({"timestamp": time.time(), "attributes": event_attributes})


    def end(self):
        if self.end_time is None:
            self.end_time = time.time()
            duration = self.end_time - self.start_time

            # Remove from current span context if it was the current one
            if self.tracer.current_span_instance == self:
                self.tracer.current_span_instance = None

class Tracer(ITracer):
    def __init__(self):
        self.current_span_instance: Optional[ISpan] = None

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> ISpan:
        span = Span(name, self, attributes)
        self.set_current_span(span)
        return span

    def current_span(self) -> Optional[ISpan]:
        return self.current_span_instance

    def set_current_span(self, span: ISpan):
        self.current_span_instance = span

# Global tracer instance (for simplicity in this example)
# In a real application, this would be managed via dependency injection or a global context manager
_global_tracer = Tracer()

def get_tracer() -> ITracer:
    return _global_tracer
