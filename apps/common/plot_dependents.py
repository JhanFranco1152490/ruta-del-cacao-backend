"""Qué depende de una parcela y cómo se elimina con ella: por ejemplo, sus actividades sin
realizar.

Es el registro de `apps.common.dependents` para parcelas; la app de parcelas lo lee al eliminar
una. Lo que no se registra aquí y apunta a la parcela (su ficha agronómica, una cosecha) sigue
impidiendo eliminarla.
"""

from .dependents import Dependent, DependentRegistry

registry = DependentRegistry()

PlotDependent = Dependent
register_dependent = registry.register
registered_dependents = registry.all
